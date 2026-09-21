"""npm・Homebrew の公開 API から生データを取得し、data/raw/<取得日 UTC>/ に保存する。

- 40 リクエスト前後、1 リクエスト/秒以下。取得済みのファイルは飛ばす（再開可）
- ダウンロード数の値は表示しない（状態コードとバイト数だけ）。集計は scripts/analyze.py
- 生データは公開しない（.gitignore 済み）

使い方:
  python scripts/fetch.py                     # 取得日 = 今日（UTC）
  python scripts/fetch.py --date 2026-09-21   # 途中で日付が変わったときの再開用
  python scripts/fetch.py --dry-run           # リクエストの一覧だけ表示
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rawlayout as L  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "ai-cli-npm-research/0.1 (personal, non-commercial; <=1 req/s; github.com/kensholog)"
RETRY_STATUS = {429, 500, 502, 503, 504}


def http_get(url: str, retries: int = 3) -> tuple[int, bytes]:
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUS:
                return e.code, e.read()
            last_err = e
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
        wait = 10 * (i + 1)
        print(f"    retry {i + 1}/{retries} after {wait}s: {last_err}")
        time.sleep(wait)
    raise RuntimeError(f"fetch failed: {url}: {last_err}")


def label(spec: dict) -> str:
    keys = ("package", "category", "type", "name", "start", "end", "period")
    return " ".join(str(spec[k]) for k in keys if k in spec)


def run(plan: list[dict], raw: Path, manifest: dict, sleep: float, offset: int, total: int) -> None:
    done = {e["file"] for e in manifest["entries"]}
    for i, spec in enumerate(plan, start=offset + 1):
        path = raw / spec["file"]
        if spec["file"] in done and path.exists():
            print(f"[{i:>2}/{total}] skip (取得済み) {spec['kind']} {label(spec)}")
            continue
        t0 = time.time()
        status, body = http_get(spec["url"])
        if status == 200:
            json.loads(body.decode("utf-8"))  # JSON として読めることだけ確認
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        entry = dict(spec)
        entry.update({
            "status": status,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest() if status == 200 else None,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        manifest["entries"] = [e for e in manifest["entries"] if e["file"] != spec["file"]] + [entry]
        (raw / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{i:>2}/{total}] {status} {len(body):>10,} bytes  {spec['kind']} {label(spec)}")
        time.sleep(max(0.0, sleep - (time.time() - t0)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="取得日（UTC、YYYY-MM-DD）。既定は今日")
    ap.add_argument("--sleep", type=float, default=1.2, help="リクエスト間隔（秒）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.sleep < 1.0:
        sys.exit("--sleep は 1.0 以上（1 リクエスト/秒以下）")

    fetch_date = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    raw = ROOT / "data" / "raw" / fetch_date.isoformat()
    stage1 = L.plan_stage1()

    if args.dry_run:
        stage2 = L.plan_stage2(fetch_date, [L.CLAUDE_PLATFORM_PREFIX + "<レジストリから決める>"])
        for spec in stage1 + stage2:
            print(spec["kind"], spec["url"])
        print(f"計 {len(stage1) + len(stage2)} リクエスト（プラットフォーム別は実際には 8 個の見込み）")
        return

    raw.mkdir(parents=True, exist_ok=True)
    mpath = raw / "manifest.json"
    if mpath.exists():
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    else:
        manifest = {
            "fetch_date_utc": fetch_date.isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "user_agent": USER_AGENT,
            "entries": [],
        }

    print(f"取得日（UTC）: {fetch_date}  集計に使う最終日: {L.last_day(fetch_date)}  保存先: {raw}")
    run(stage1, raw, manifest, args.sleep, 0, len(stage1))
    claude_reg = json.loads((raw / f"registry/{L.slug(L.PACKAGES['claude'])}.json").read_text(encoding="utf-8"))
    platform_pkgs = L.claude_platform_packages(claude_reg)
    print(f"Claude Code のプラットフォーム別パッケージ: {len(platform_pkgs)} 個")
    stage2 = L.plan_stage2(fetch_date, platform_pkgs)
    total = len(stage1) + len(stage2)
    run(stage2, raw, manifest, args.sleep, len(stage1), total)

    manifest["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [e for e in manifest["entries"] if e["status"] != 200]
    print(f"完了: {len(manifest['entries'])} 件、うち 200 以外 {len(bad)} 件")
    for e in bad:
        print(f"  {e['status']} {e['url']}")


if __name__ == "__main__":
    main()

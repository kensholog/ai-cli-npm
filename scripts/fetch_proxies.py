"""decisions/0003 の代理指標を取得して data/proxies/<取得日 UTC>/ に保存する。

- GitHub（issue は GraphQL、Releases は REST）は、認証済みの `gh` コマンドを呼ぶ（トークンをこのスクリプトでは扱わない）
- Hacker News（Algolia の公開 API）、npm（関連パッケージの日次）、OpenAI の変更履歴ページは urllib
- 1 リクエスト/秒以下。途中で止めても再開できる。**件数・ダウンロード数などの値は表示しない**（進み具合だけ）
- 生データは公開しない（.gitignore 済み）

使い方:
  python scripts/fetch_proxies.py                    # 全部
  python scripts/fetch_proxies.py --only hn,npm      # 一部だけ（issues, releases, hn, npm, changelog）
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proxy_metrics as M  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "ai-cli-npm-research/0.1 (personal, non-commercial; <=1 req/s; github.com/kensholog)"
GH = shutil.which("gh")
SLEEP = 1.1
HN_START, LAST_DAY = date(2025, 10, 1), date(2026, 9, 19)
NPM_RELATED = ("@openai/codex-sdk", "openai", "@openai/agents")
CHANGELOG_URL = "https://learn.chatgpt.com/docs/changelog"

ISSUES_QUERY = """
query($owner:String!, $name:String!, $after:String) {
  repository(owner:$owner, name:$name) {
    issues(first:100, after:$after, orderBy:{field:CREATED_AT, direction:ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes { number createdAt title author { login __typename } }
    }
  }
}
"""
RELEASES_JQ = ("[.[] | {tag_name, name, published_at, created_at, prerelease, draft, body, "
               "assets: [.assets[] | {name, download_count, size}]}]")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(s: str) -> str:
    return s.lstrip("@").replace("/", "__")


class Log:
    def __init__(self, out: Path):
        self.path = out / "manifest.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {
            "fetch_date_utc": out.name, "started_at": now(), "user_agent": USER_AGENT, "requests": []}
        self.last = 0.0

    def wait(self):
        time.sleep(max(0.0, SLEEP - (time.time() - self.last)))
        self.last = time.time()

    def add(self, **kw):
        self.data["requests"].append({**kw, "at": now()})
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")


def gh(args: list[str], log: Log, kind: str, what: str, retries: int = 3) -> str:
    for i in range(retries):
        log.wait()
        p = subprocess.run([GH, "api", *args], capture_output=True, text=True, encoding="utf-8")
        log.add(kind=kind, what=what, exit=p.returncode, bytes=len(p.stdout))
        if p.returncode == 0:
            return p.stdout
        print(f"    gh 失敗（{i + 1}/{retries}）: {p.stderr.strip()[:200]}")
        time.sleep(20 * (i + 1))
    raise RuntimeError(f"gh api failed: {what}")


def http(url: str, log: Log, kind: str, retries: int = 3) -> tuple[int, bytes]:
    for i in range(retries):
        log.wait()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
                log.add(kind=kind, url=url, status=r.status, bytes=len(body))
                return r.status, body
        except urllib.error.HTTPError as e:
            body = e.read()
            log.add(kind=kind, url=url, status=e.code, bytes=len(body))
            if e.code not in (429, 500, 502, 503, 504):
                return e.code, body
        except (urllib.error.URLError, TimeoutError) as e:
            log.add(kind=kind, url=url, status=None, error=str(e)[:200])
        time.sleep(20 * (i + 1))
    raise RuntimeError(f"fetch failed: {url}")


def fetch_issues(out: Path, log: Log) -> None:
    for tool, repo in M.REPOS.items():
        owner, name = repo.split("/")
        path, state_path = out / "issues" / f"{slug(repo)}.jsonl", out / "issues" / f"{slug(repo)}.state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"after": None, "done": False, "pages": 0}
        while not state["done"]:
            args = ["graphql", "-f", f"query={ISSUES_QUERY}", "-f", f"owner={owner}", "-f", f"name={name}"]
            if state["after"]:
                args += ["-f", f"after={state['after']}"]
            body = json.loads(gh(args, log, "issues", f"{repo} page {state['pages'] + 1}"))
            conn = body["data"]["repository"]["issues"]
            with open(path, "a", encoding="utf-8") as f:
                for node in conn["nodes"]:
                    f.write(json.dumps(node, ensure_ascii=False) + "\n")
            state = {"after": conn["pageInfo"]["endCursor"], "done": not conn["pageInfo"]["hasNextPage"], "pages": state["pages"] + 1}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            if state["pages"] % 20 == 0:
                print(f"  issues {repo}: {state['pages']} ページ")
        print(f"issues {repo}: 完了")


def fetch_releases(out: Path, log: Log) -> None:
    for tool, repo in M.REPOS.items():
        path = out / "releases" / f"{slug(repo)}.json"
        if path.exists():
            print(f"releases {repo}: 取得済み")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        rows, page, started = [], 1, now()
        while True:
            got = json.loads(gh([f"repos/{repo}/releases?per_page=30&page={page}", "--jq", RELEASES_JQ], log, "releases", f"{repo} page {page}"))
            if not got:
                break
            rows += got
            page += 1
        path.write_text(json.dumps({"repo": repo, "fetched_at": started, "releases": rows}, ensure_ascii=False), encoding="utf-8")
        print(f"releases {repo}: 完了（{page - 1} ページ）")


def hn_chunk(tool: str, s: datetime, e: datetime, log: Log) -> list[dict]:
    q = urllib.parse.quote(M.HN_QUERY[tool])
    nf = urllib.parse.quote(f"created_at_i>={int(s.timestamp())},created_at_i<{int(e.timestamp())}")
    url = f"https://hn.algolia.com/api/v1/search_by_date?query={q}&tags=story&numericFilters={nf}&hitsPerPage=1000&page=0"
    status, body = http(url, log, "hn")
    if status != 200:
        raise RuntimeError(f"HN {status}")
    d = json.loads(body)
    if d["nbHits"] > len(d["hits"]):  # 1 回で取り切れない → 期間を半分に割る
        mid = s + (e - s) / 2
        return hn_chunk(tool, s, mid, log) + hn_chunk(tool, mid, e, log)
    return [{"objectID": h["objectID"], "title": h.get("title"), "created_at_i": h["created_at_i"],
             "points": h.get("points"), "num_comments": h.get("num_comments")} for h in d["hits"]]


def fetch_hn(out: Path, log: Log) -> None:
    months, d = [], HN_START
    while d <= LAST_DAY:
        nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        months.append((d, min(nxt - timedelta(days=1), LAST_DAY)))
        d = nxt
    for tool in M.TOOLS:
        path = out / "hn" / f"{tool}.json"
        if path.exists():
            print(f"hn {tool}: 取得済み")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        hits = []
        for p in months:
            s, e = M.bounds(p)
            hits += hn_chunk(tool, s, e, log)
        path.write_text(json.dumps({"tool": tool, "query": M.HN_QUERY[tool], "period": [HN_START.isoformat(), LAST_DAY.isoformat()], "hits": hits},
                                   ensure_ascii=False), encoding="utf-8")
        print(f"hn {tool}: 完了")


def fetch_npm(out: Path, log: Log) -> None:
    for pkg in NPM_RELATED:
        path = out / "npm_related" / f"{slug(pkg)}.json"
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        status, body = http(f"https://api.npmjs.org/downloads/range/2026-04-01:2026-05-31/{pkg}", log, "npm_related")
        path.write_text(json.dumps({"package": pkg, "status": status, "body": json.loads(body) if status == 200 else None}), encoding="utf-8")
        print(f"npm {pkg}: {status}")


def fetch_changelog(out: Path, log: Log) -> None:
    path = out / "changelog.html"
    if path.exists():
        return
    status, body = http(CHANGELOG_URL, log, "changelog")
    path.write_bytes(body)
    print(f"changelog: {status}、{len(body):,} bytes")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="取得日（UTC）。既定は今日")
    ap.add_argument("--only", default="issues,releases,hn,npm,changelog")
    args = ap.parse_args()
    if not GH:
        sys.exit("gh コマンドが見つからない")
    out = ROOT / "data" / "proxies" / (args.date or datetime.now(timezone.utc).date().isoformat())
    out.mkdir(parents=True, exist_ok=True)
    log = Log(out)
    steps = {"npm": fetch_npm, "changelog": fetch_changelog, "hn": fetch_hn, "releases": fetch_releases, "issues": fetch_issues}
    for name in ("npm", "changelog", "hn", "releases", "issues"):
        if name in args.only.split(","):
            steps[name](out, log)
    log.data["finished_at"] = now()
    log.add(kind="done", what=args.only)
    print(f"完了: リクエスト {len(log.data['requests'])} 件 → {out}")


if __name__ == "__main__":
    main()

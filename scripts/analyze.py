"""生データ（data/raw/<取得日>/）を集計して、判定を表示し、docs/data/ に公開用の集計を書く。

  python scripts/analyze.py                          # data/raw/ の最新の取得日
  python scripts/analyze.py --raw <dir> --out <dir>  # 合成データでの動作確認など

定義・窓・閾値は docs/decisions/0001 のとおり（実装は metrics.py）。事前登録に無い集計はここに足さない。
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metrics as M  # noqa: E402
import rawlayout as L  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
NAME = {"claude": "Claude Code", "codex": "Codex CLI", "gemini": "Gemini CLI"}


def f(x, nd=3):
    return "―" if x is None else f"{x:,.{nd}f}" if isinstance(x, float) else f"{x:,}"


def w(win):
    return f"{win[0]}〜{win[1]}" if win else "―"


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fp:
        wr = csv.writer(fp, lineterminator="\n")
        wr.writerow(header)
        wr.writerows(rows)


def report(r: dict) -> None:
    print(f"取得日（UTC） {r['fetch_date_utc']} / 集計の最終日 {r['last_day']} / リクエスト {r['n_requests']} 件、200 以外 {len(r['non_200'])} 件")
    for x in r["non_200"]:
        print(f"  {x['status']} {x['url']}")

    print(f"\n[A] データ到達: {'通過' if r['A']['ok'] else '不通過'}")
    for t, a in r["A"]["per_tool"].items():
        print(f"  {NAME[t]}: 公開日 {a.get('pub_date')}〜{a.get('last_day')} の {f(a.get('n_expected'))} 日、欠け {a.get('n_missing')} 日"
              f"（最初の非ゼロ日 {a.get('first_nonzero')}、その後の 0 の日 {a.get('n_zero_days_after_first_nonzero')} 日）"
              f" / 安定版 {a.get('n_stable_time')}（versions に残るもの {a.get('n_stable_listed')}）、公開時刻の無い安定版 {len(a.get('stable_missing_time', []))}"
              f"、最後の安定版 {a.get('last_stable_date')}")
        if a.get("missing_dates"):
            print(f"    欠けた日: {a['missing_dates']}")
        if a.get("zero_days"):
            print(f"    0 の日: {a['zero_days']}")
    print(f"[B] range と point（{w(r['B']['window'])}）: {'通過' if r['B']['ok'] else '不通過'}")
    for t, b in r["B"]["per_tool"].items():
        print(f"  {NAME[t]}: range 合計 {f(b['range_sum'])} / point {f(b['point'])} / 差 {f(b['rel_diff'] * 100 if b['rel_diff'] is not None else None, 4)}%")
    if "P1a" not in r:
        print("\nA が不通過のため、予測の集計はしない")
        return

    p = r["P1a"]
    print(f"\n[P1a] Codex の版別（直近 7 日）: s = {f(p['s'], 4)} → {p['verdict']}（0.40 以上で支持、0.20 未満で不支持）")
    if p.get("total") is not None:
        print(f"  全版 {f(p['total'])}（キー {f(p['n_keys'])}）= 安定版 {f(p['stable_total'])} ＋ プラットフォーム版 {f(p['platform_total'])}（キー {f(p['n_platform_keys'])}）"
              f" ＋ その他のプレリリース {f(p['other_prerelease_total'])}")
        print("  接尾辞別: " + "、".join(f"{k[1:]} {f(v)}" for k, v in p["by_suffix"].items()))
    for t, x in r["P1a_reference_other_tools"].items():
        print(f"  （参考）{NAME[t]}: 全版 {f(x['total'])}、プラットフォーム接尾辞つき {f(x['platform_total'])}")
    for t, x in r["versions_total_vs_point_lastweek"].items():
        print(f"  （参考）{NAME[t]}: 版別の合計 {f(x['versions_total'])} / point last-week {f(x['point_lastweek'])}（{w(x['point_window'])}）")

    p = r["P1b"]
    print(f"\n[P1b] E = {M.E_CODEX} の前後（前 {w(M.P1B_BEFORE)}、後 {w(M.P1B_AFTER)}）: 差の差 = {f(p['did'])} → {p['verdict']}（1.5 以上で支持、1.2 未満で不支持）")
    for t, x in p["per_tool"].items():
        print(f"  {NAME[t]}: 中央値 {f(x['median_before'])} → {f(x['median_after'])}、比 {f(x['ratio'])}")
    print(f"  他 2 つの比の算術平均 {f(p['others_mean'])}")

    print(f"\n[P2] リリース日と翌日の平日 ÷ それ以外の平日（{w(r['P2']['codex']['window'])}、1.2 以上で跳ねる、どちらかが 20 日未満なら判定不能）")
    for t, x in r["P2"].items():
        print(f"  {NAME[t]}: リリース日 {x['n_release_days_in_window']} 日 / 群の日数 {x['n_release']}・{x['n_other']} / 中央値 {f(x['median_release'])}・{f(x['median_other'])}"
              f" / 比 {f(x['ratio'])} → {x['verdict']}")

    p = r["P3"]
    print("\n[P3] npm と Homebrew の順位（判定なし）")
    if "dropped" in p:
        print(f"  {p['dropped']}")
    else:
        c = p["codex_formula"]
        print(f"  formula codex: {c['reason']} → {'足す' if c['same_tool'] else '足さない'}（homepage {c['homepage']} / desc {c['desc']}）")
        for period, x in p["periods"].items():
            print(f"  {period}: npm（{w(x['npm_window'])}） " + " / ".join(f"{NAME[t]} {f(x['npm'][t])}" for t in L.TOOLS)
                  + f" → {x['npm_rank']}")
            print(f"       Homebrew（{w(x['brew_window'])}） " + " / ".join(f"{NAME[t]} {f(x['brew'][t])}" for t in L.TOOLS)
                  + f" → {x['brew_rank']} / 順位は{'一致' if x['same_order'] else '不一致' if x['same_order'] is False else '―'}")
            print(f"       内訳 {x['brew_parts']}")
        print(f"  （参考）formula の install-on-request: {p['reference_install_on_request']}")

    d = r["desc"]
    a = d["a_claude_platform_share"]
    print(f"\n[記述 a] Claude Code のプラットフォーム別 {len(a['totals'])} パッケージ（{w(a['window'])}）: 合計 {f(a['total'])}、Linux の割合 {f(a['linux_share'])}")
    for k, v in sorted(a["totals"].items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {f(v)}（{f(a['shares'][k])}）")
    print("[記述 b] 平日 ÷ 週末（中央値、直近 180 日）: " + " / ".join(f"{NAME[t]} {f(d['b_weekday_weekend'][t]['ratio'])}" for t in L.TOOLS))
    c = d["c_claude_split"]["claude"]
    print(f"[記述 c] 2026-04-13 の前後（前 {w(c['before'])}、後 {w(c['after'])}）: "
          + " / ".join(f"{NAME[t]} {f(d['c_claude_split'][t]['median_before'])} → {f(d['c_claude_split'][t]['median_after'])}（比 {f(d['c_claude_split'][t]['ratio'])}）" for t in L.TOOLS))
    print("[記述 d] 火・水 ÷ 他の平日（中央値、直近 180 日）: " + " / ".join(f"{NAME[t]} {f(d['d_tue_wed'][t]['ratio'])}" for t in L.TOOLS))
    rc = r["registry_checks"]
    print(f"[レジストリとの突き合わせ] Codex で別名の指定が最初に出る安定版: {rc['codex_first_alias_version']} / "
          f"Claude Code で別パッケージの指定が最初に出る版: {rc['claude_first_platform_dep_version']}")
    print(f"\n[C] 新規性: {'満たす' if r['C']['ok'] else '満たさない'}（結果が出たもの: {r['C']['determinate']}）")


def write_outputs(r: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(M.to_jsonable(r), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if "P1a" not in r:
        return
    dailies, rel = r["_dailies"], r["_release_days"]
    start = min(a["pub_date"] for a in r["A"]["per_tool"].values())
    write_csv(out / "daily_downloads.csv", ["day", *L.TOOLS],
              [[d.isoformat(), *[dailies[t].get(d, "") for t in L.TOOLS]] for d in M.days((start, r["last_day"]))])
    write_csv(out / "release_days.csv", ["tool", "day", "n_stable_versions"],
              [[t, d.isoformat(), n] for t in L.TOOLS for d, n in sorted(rel[t].items())])
    p = r["P1a"]
    if p.get("total"):
        rows = [["stable", p["stable_total"]], *[[f"platform{k}", v] for k, v in p["by_suffix"].items()],
                ["other_prerelease", p["other_prerelease_total"]], ["total", p["total"]]]
        write_csv(out / "codex_versions_lastweek.csv", ["category", "downloads", "share"],
                  [[k, v, f"{v / p['total']:.6f}"] for k, v in rows])
    a = r["desc"]["a_claude_platform_share"]
    write_csv(out / "claude_platform_30d.csv", ["package", "downloads_30d", "share"],
              [[k, v, f"{a['shares'][k]:.6f}"] for k, v in sorted(a["totals"].items(), key=lambda kv: -kv[1])])
    if "periods" in r["P3"]:
        rows = []
        for period, x in r["P3"]["periods"].items():
            for t in L.TOOLS:
                rows.append([period, t, x["npm"][t], (x["npm_rank"].index(t) + 1) if x["npm_rank"] else "",
                             x["brew"][t] if x["brew"][t] is not None else "", (x["brew_rank"].index(t) + 1) if x["brew_rank"] else ""])
        write_csv(out / "p3_npm_vs_homebrew.csv", ["period", "tool", "npm_downloads", "npm_rank", "homebrew_installs", "homebrew_rank"], rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", help="生データのフォルダ。既定は data/raw/ の最新")
    ap.add_argument("--out", help="出力先。既定は docs/data/")
    args = ap.parse_args()
    raw = Path(args.raw) if args.raw else sorted((ROOT / "data" / "raw").iterdir())[-1]
    r = M.analyze(raw)
    report(r)
    write_outputs(r, Path(args.out) if args.out else ROOT / "docs" / "data")


if __name__ == "__main__":
    main()

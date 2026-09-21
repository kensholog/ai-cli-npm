"""decisions/0005 の判定（R1a・R1m・R1b・R3c・R3x）と記述（R2・R4・対照・比較表）を出す。

  python scripts/analyze_moved.py        # docs/data/moved_summary.json、moved_weekly.csv に書く

issue の題名は data/proxies/2026-09-21/issues/（2026-09-21 取得）、issue の状態は data/issue_states/ の最新。
定義・期間・閾値・語の規則は docs/decisions/0005（実装は moved_metrics.py）。0005 に無い集計はここに足さない。
"""
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moved_metrics as M  # noqa: E402
import proxy_metrics as PM  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "proxies" / "2026-09-21"
NAME = {"codex": "Codex CLI", "claude": "Claude Code", "gemini": "Gemini CLI"}
LABEL = {"model": "[MODEL]", "quality": "「品質」語", "limits": "「利用枠・料金」語", "other": "それ以外"}


def slug(s):
    return s.replace("/", "__")


def pct(x):
    return "―" if x is None else f"{x * 100:.2f}%"


def main() -> None:
    issues = {t: PM.load_jsonl(RAW / "issues" / f"{slug(r)}.jsonl") for t, r in PM.REPOS.items()}
    hits = {t: json.loads((RAW / "hn" / f"{t}.json").read_text(encoding="utf-8"))["hits"] for t in PM.TOOLS}
    out: dict = {}

    tests = {"R1a": ("claude", "quality", (M.P1,)), "R1m": ("claude", "model", (M.P1,)), "R1b": ("claude", "limits", (M.P1,)),
             "R3c": ("claude", "other_from_claude", (M.P1, M.P2)), "R3x": ("codex", "other_from_codex", (M.P1, M.P2))}
    print("[判定] 割合の比（1.5 以上で支持、1.2 未満で不支持。P0 の該当が 20 件未満なら判定不能）")
    for k, (tool, key, num) in tests.items():
        r = M.share_ratio(issues[tool], key, num)
        out[k] = {"tool": tool, "rule": key, **r}
        n, d = r["numerator"], r["denominator"]
        print(f"  {k}（{NAME[tool]}・{key}）: P0 {d['n_match']:,} / {d['n_total']:,}（{pct(d['share'])}）→ {n['n_match']:,} / {n['n_total']:,}（{pct(n['share'])}）"
              f"  比 {r['ratio']:.2f} → {r['verdict']}" if r["ratio"] is not None else f"  {k}: 判定不能")

    print("\n[対照] 同じ比を他のリポジトリにも（記述）")
    out["control"] = {}
    for tool in ("codex", "gemini"):
        out["control"][tool] = {key: M.share_ratio(issues[tool], key, (M.P1,)) for key in ("quality", "limits")}
        for key, r in out["control"][tool].items():
            print(f"  {NAME[tool]}・{key}: {pct(r['denominator']['share'])}（{r['denominator']['n_match']:,} 件）→ {pct(r['numerator']['share'])}（{r['numerator']['n_match']:,} 件）"
                  f"  比 {r['ratio']:.2f}" if r["ratio"] is not None else f"  {NAME[tool]}・{key}: 比が出ない")
    # P2 の割合も並べる（記述）
    out["shares_by_period"] = {t: {key: {p: M.share(issues[t], (per,), M.matcher(key)) for p, per in M.PERIODS.items()}
                                   for key in (["model"] if t == "claude" else []) + ["quality", "limits", "other_from_claude" if t == "claude" else "other_from_codex"]}
                               for t in PM.TOOLS}
    print("\n[割合の推移] P0 → P1 → P2（記述）")
    for t, m in out["shares_by_period"].items():
        for key, by in m.items():
            print(f"  {NAME[t]}・{key}: " + " → ".join(f"{pct(by[p]['share'])}（{by[p]['n_match']:,}）" for p in M.PERIODS))

    print("\n[R2] 週あたりの件数の内訳（重なりは [MODEL] → 品質 → 利用枠の順で除く）")
    out["R2"] = {}
    for t in PM.TOOLS:
        out["R2"][t] = {p: M.breakdown(issues[t], per, with_model=(t == "claude")) for p, per in M.PERIODS.items()}
        for k in out["R2"][t]["P0"]["counts"]:
            print(f"  {NAME[t]}・{LABEL[k]}: " + " → ".join(f"{out['R2'][t][p]['per_week'][k]:,.0f}" for p in M.PERIODS))
        print(f"  {NAME[t]}・合計: " + " → ".join(f"{out['R2'][t][p]['total_per_week']:,.0f}" for p in M.PERIODS))

    print("\n[R4] `5.5` への言及（週別。月曜はじまり）と、Hacker News の上位 5 本")
    start, end = date(2026, 3, 30), date(2026, 5, 31)
    wk = M.weekly_counts(issues["codex"], start, end, ["gpt55"], with_model=False)
    out["R4"] = {"codex_issue_titles_5_5_weekly": wk, "hn_top": {}}
    hn55 = {}
    for h in hits["codex"]:
        if PM.HN_RE["codex"].search(h.get("title") or "") and M.RX["gpt55"].search(h.get("title") or ""):
            d = datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc).date()
            hn55[d.isoformat()[:7]] = hn55.get(d.isoformat()[:7], 0) + 1
    out["R4"]["hn_codex_titles_5_5_by_month"] = hn55
    print("  codex の issue の題名（週の始まり: 件数 / その週の全件）: " + "、".join(f"{r['week_start']:%m-%d}: {r['gpt55']}/{r['total']}" for r in wk))
    print(f"  codex の Hacker News の題名（月別）: {hn55}")
    for t in PM.TOOLS:
        out["R4"]["hn_top"][t] = {p: M.hn_top(hits[t], t, per) for p, per in M.PERIODS.items()}
        for p in M.PERIODS:
            print(f"  {NAME[t]} {p}: " + " / ".join(f"{h['points']}点「{h['title'][:70]}」" for h in out["R4"]["hn_top"][t][p]))

    # 週次の系列（図用）
    rows = []
    for t in PM.TOOLS:
        keys = (["model"] if t == "claude" else []) + ["quality", "limits", "other_from_claude" if t == "claude" else "other_from_codex"]
        for r in M.weekly_counts(issues[t], date(2025, 12, 29), date(2026, 6, 28), keys, with_model=(t == "claude")):
            rows.append([t, r["week_start"].isoformat(), r["total"], r.get("model", ""), r["quality"], r["limits"], r.get("other_from_claude", r.get("other_from_codex", ""))])
    with open(ROOT / "docs" / "data" / "moved_weekly.csv", "w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp, lineterminator="\n")
        w.writerow(["tool", "week_start_mon", "issues", "model_prefix", "quality_words", "limits_words", "mentions_other_tool"])
        w.writerows(rows)

    # 比較表: issue への対応
    sdirs = sorted((ROOT / "data" / "issue_states").iterdir()) if (ROOT / "data" / "issue_states").exists() else []
    out["handling"] = {}
    if sdirs:
        print(f"\n[比較表] issue への対応（{M.HANDLING[0]}〜{M.HANDLING[1]} に作られた Bot 以外の issue。状態の取得 {sdirs[-1].name}）")
        for t, r in PM.REPOS.items():
            p = sdirs[-1] / f"{slug(r)}.jsonl"
            if p.exists():
                h = M.handling(PM.load_jsonl(p))
                out["handling"][t] = h
                print(f"  {NAME[t]}: {h['n']:,} 件 / 閉じた {pct(h['closed_share'])} / 7 日以内 {pct(h['closed_within_7d_share'])} / 30 日以内 {pct(h['closed_within_30d_share'])}"
                      f" / 中央値 {h['median_days_to_close']:.1f} 日 / 理由 { {k: round(v, 3) for k, v in h['reasons_among_closed'].items()} }"
                      f" / コメントあり {pct(h['commented_share'])}（中央値 {h['median_comments']}）")

    (ROOT / "docs" / "data" / "moved_summary.json").write_text(json.dumps(PM.to_jsonable(out), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

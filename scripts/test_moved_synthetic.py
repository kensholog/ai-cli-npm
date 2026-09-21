"""答えの分かっている合成データで moved_metrics.py を検証する（実データの題名に当てる前に通す）。

  python scripts/test_moved_synthetic.py

合成データ（claude-code 役）: Bot 以外の issue を P0 に 1,000 件、P1 に 2,000 件、P2 に 1,000 件。
- 「品質」語: P0 50 件（5%）→ P1 200 件（10%）→ 比 2.0（支持）
- `[MODEL]` 接頭辞: P0 40 件（4%）→ P1 100 件（5%）→ 比 1.25（保留）。うち P1 の 30 件は題名に「品質」語も含む（R1a には数え、R2 の内訳では [MODEL] に入れる）
- 「利用枠・料金」語: P0 30 件（3%）→ P1 66 件（3.3%）→ 比 1.1（不支持）
- 相手への言及: P0 20 件（2%）→ P1 80 件 ＋ P2 40 件 = 120 / 3,000（4%）→ 比 2.0（支持）
- Bot の issue（「品質」語つき）を各期間に 500 件、期間の外（04-21・04-22・05-28）にも該当する題名を置く
"""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moved_metrics as M  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
FAILS: list[str] = []
N = 0


def check(name, got, want, tol=0.0):
    global N
    N += 1
    ok = (got is not None and abs(got - want) <= tol) if tol else got == want
    if not ok:
        FAILS.append(name)
    print(f"  {'ok ' if ok else 'NG '} {name}: {got!r}" + ("" if ok else f"  (期待 {want!r})"))


def ts(d: date, h=12, m=0, s=0) -> str:
    return datetime(d.year, d.month, d.day, h, m, s, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def make() -> list[dict]:
    out = []

    def add(d, title, typename="User", **kw):
        out.append({"number": len(out) + 1, "createdAt": ts(d, **kw), "title": title, "author": {"login": f"u{len(out)}", "__typename": typename}})

    def fill(p, spec: dict[str, int], total: int):
        days = (p[1] - p[0]).days + 1
        k = 0
        for t, n in spec.items():
            for _ in range(n):
                add(p[0] + timedelta(days=k % days), t)
                k += 1
        for _ in range(total - sum(spec.values())):
            add(p[0] + timedelta(days=k % days), "[BUG] terminal flickers on resize")
            k += 1
        for _ in range(500):
            add(p[0], "quality is worse (bot)", "Bot")

    fill(M.P0, {"Claude got dumber": 50, "[MODEL] refuses to edit files": 40, "Rate limit reached too fast": 30, "Support GPT-5 like Codex does": 20}, 1000)
    fill(M.P1, {"Output quality degraded": 170, "[MODEL] quality is worse than last week": 30, "[MODEL] stops mid task": 70,
                "Weekly limit hit after 2 hours": 66, "Switching to codex": 80}, 2000)
    fill(M.P2, {"Moving to OpenAI": 40}, 1000)
    # 期間の端と外
    out[0]["createdAt"] = ts(M.P0[0], h=0)                      # 01-07 00:00:00 は P0
    add(date(2026, 3, 3), "[BUG] edge", h=23, m=59, s=59)       # P0 の最後の 1 秒（分母 +1）
    for d in (date(2026, 4, 21), date(2026, 4, 22), date(2026, 5, 28), date(2026, 1, 6)):
        add(d, "[MODEL] quality is worse, hit the limit, going to codex")
    return out


def main():
    issues = make()
    print("== 期間")
    check("日数", [M.PM.n_days(p) for p in (M.P0, M.P1, M.P2)], [56, 48, 35])
    print("== 判定に使う比")
    r = M.share_ratio(issues, "quality", (M.P1,))
    check("R1a 分母（P0: 50 / 1,001）", (r["denominator"]["n_match"], r["denominator"]["n_total"]), (50, 1001))
    check("R1a 分子（P1: 200 / 2,000）", (r["numerator"]["n_match"], r["numerator"]["n_total"]), (200, 2000))
    check("R1a 比と判定", (round(r["ratio"], 4), r["verdict"]), (round(0.10 / (50 / 1001), 4), "支持"))
    r = M.share_ratio(issues, "model", (M.P1,))
    check("R1m（100 / 2,000 ÷ 40 / 1,001）", (r["numerator"]["n_match"], r["denominator"]["n_match"], r["verdict"]), (100, 40, "保留"))
    r = M.share_ratio(issues, "limits", (M.P1,))
    check("R1b（66 / 2,000 ÷ 30 / 1,001）", (r["numerator"]["n_match"], r["denominator"]["n_match"], r["verdict"]), (66, 30, "不支持"))
    r = M.share_ratio(issues, "other_from_claude", (M.P1, M.P2))
    check("R3c 分子は P1 ＋ P2", (r["numerator"]["n_match"], r["numerator"]["n_total"]), (120, 3000))
    check("R3c 判定", r["verdict"], "支持")

    print("== 判定の境界")
    check("1.5", M.verdict(1.5, 20), "支持")
    check("1.49", M.verdict(1.49, 500), "保留")
    check("1.2", M.verdict(1.2, 500), "保留")
    check("1.19", M.verdict(1.19, 500), "不支持")
    check("P0 の該当が 19 件", M.verdict(3.0, 19), "判定不能")
    check("比が出ない", M.verdict(None, 500), "判定不能")

    print("== R2 の内訳（重なりは [MODEL] を優先）")
    b = M.breakdown(issues, M.P1, with_model=True)
    check("P1 の内訳", b["counts"], {"model": 100, "quality": 170, "limits": 66, "other": 1664})
    check("P1 の週あたり（それ以外）", b["per_week"]["other"], 1664 / 48 * 7, 1e-9)
    b = M.breakdown(issues, M.P1, with_model=False)
    check("[MODEL] を使わない内訳（codex 用）", b["counts"], {"quality": 200, "limits": 66, "other": 1734})

    print("== 語の規則")
    cases = {
        "quality": {"Claude Code got dumber after the update": True, "Forgets context every turn": True, "[MODEL] ignores CLAUDE.md rules": True,
                    "Does not follow instructions": True, "doesn't follow the plan": True, "IntelliJ plugin crashes": False, "Add nerd font support": False},
        "limits": {"Rate limit reached after 3 prompts": True, "5-hour limit resets incorrectly": True, "Pricing page is wrong": True,
                   "Enterprise SSO login fails": False, "Hit my limit in 10 minutes": True, "Max plan usage drain": True, "Surprise: works great": False},
        "other_from_claude": {"Add GPT-5 support": True, "Compare with Codex CLI": True, "ChatGPT style sidebar": True, "Open AI assistant panel": False},
        "other_from_codex": {"Import CLAUDE.md like Claude Code": True, "Opus is better at this": True, "Octopus merge fails": False, "Sonnet-style output": True, "personnet": False},
    }
    for key, m in cases.items():
        for t, want in m.items():
            check(f"{key}: {t}", bool(M.RX[key].search(t)), want)
    check("[MODEL] 接頭辞（前の空白と小文字）", [M.is_model({"title": t}) for t in ("[MODEL] x", "  [model] x", "Remodel [MODEL]", None)], [True, True, False, False])

    print("== 週次と Hacker News の上位")
    w = M.weekly_counts(issues, date(2026, 3, 4), date(2026, 3, 17), ["model", "quality"], with_model=True)
    check("週の数と列", (len(w), sorted(w[0])), (2, ["model", "quality", "total", "week_start"]))
    hits = [{"objectID": str(k), "title": "Codex update", "points": p, "created_at_i": int(datetime(2026, 3, 10, tzinfo=timezone.utc).timestamp()) + k}
            for k, p in enumerate([5, 50, 50, 7, 1, 3, 9])]
    hits.append({"objectID": "99", "title": "Unrelated", "points": 999, "created_at_i": hits[0]["created_at_i"]})
    check("上位 5 本（ポイント順、同点は古い順）", [h["points"] for h in M.hn_top(hits, "codex", M.P1)], [50, 50, 9, 7, 5])

    print("== 比較表（issue への対応）")
    def st(created, closed=None, reason=None, comments=0, typename="User"):
        return {"createdAt": ts(created), "closedAt": ts(closed) if closed else None, "state": "CLOSED" if closed else "OPEN",
                "stateReason": reason, "comments": {"totalCount": comments}, "author": {"__typename": typename}}
    d = date(2026, 7, 1)
    states = [st(d, d + timedelta(days=1), "COMPLETED", 2), st(d, d + timedelta(days=7), "NOT_PLANNED", 1), st(d, d + timedelta(days=8), "DUPLICATE", 0),
              st(d, d + timedelta(days=40), "COMPLETED", 5), st(d), st(d, None, None, 3), st(d), st(d), st(d), st(d),
              st(d, d + timedelta(days=1), "COMPLETED", 9, "Bot"), st(date(2026, 5, 31), date(2026, 6, 2), "COMPLETED", 1), st(date(2026, 9, 1))]
    h = M.handling(states)
    check("対象は 10 件（Bot と期間外を除く）", h["n"], 10)
    check("閉じた割合・7 日以内・30 日以内", (h["closed_share"], h["closed_within_7d_share"], h["closed_within_30d_share"]), (0.4, 0.2, 0.3))
    check("閉じるまでの日数の中央値（1・7・8・40 → 7.5）", h["median_days_to_close"], 7.5)
    check("閉じた理由", h["reasons_among_closed"], {"COMPLETED": 0.5, "DUPLICATE": 0.25, "NOT_PLANNED": 0.25})
    check("コメントあり・中央値", (h["commented_share"], h["median_comments"]), (0.4, 0.0))

    print(f"\n{N - len(FAILS)}/{N} 通過" + ("" if not FAILS else f"、NG: {FAILS}"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()

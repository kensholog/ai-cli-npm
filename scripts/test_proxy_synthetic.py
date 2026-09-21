"""答えの分かっている合成データで proxy_metrics.py を検証する（実データに当てる前に通す）。

  python scripts/test_proxy_synthetic.py

合成データの作り:
- issue（人）: 直前 4 週は各 100 件、突出の週は 200 件（うち 1 件は作成者なし）→ 週の比 2.0。Bot の issue を各週 5 件・突出の週 50 件まぜる（数えたら 2.38 になる）
  初めての人は直前 4 週が各 40 人、突出の週が 50 人 → 1.25。残りは 1 月に初投稿した常連 10 人
  2026-01 は 50 人 × 2 件 = 100 件、2026-08 は 100 人 × 3 件 = 300 件 → 月の比は件数 3.0、人数 2.0
- Releases: 04-02・09・16・23 の安定版が各 700（7 日間ずつ最新）→ 100/日。04-30〜05-07 が最新だった版が 2,100 → 300/日 → 週の比 3.0
  2026-01 は 3,100（31 日）→ 100/日、2026-08 は 31,000 → 1,000/日 → 月の比 10.0。プレリリースと draft は巨大な値でも無視
- Hacker News: 直前 4 週は各 10 本、突出の週は 12 本（同じ objectID の重複 1 本、題名が合わないもの 5 本をまぜる）→ 1.2。1 月 10 本、8 月 40 本 → 4.0
→ Q1 は 1.5 以上が 4 個中 2 個で「保留」、Q2 は中央値 3.5 で「支持」
"""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proxy_metrics as M  # noqa: E402

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


def make_issues() -> list[dict]:
    out, n = [], 0

    def add(d, login, typename="User", **kw):
        nonlocal n
        n += 1
        out.append({"number": n, "createdAt": ts(d, **kw), "title": f"issue {n}",
                    "author": None if login is None else {"login": login, "__typename": typename}})

    for j in range(50):  # 1 月: 50 人 × 2 件
        add(date(2026, 1, 5), f"j{j}")
        add(date(2026, 1, 20), f"j{j}")
    for k, (s, _) in enumerate(M.BASE_WEEKS):
        for a in range(40):
            add(s + timedelta(days=a % 7), f"w{k}_{a}")
        for a in range(60):
            add(s + timedelta(days=a % 7), f"j{a % 10}")
        for a in range(5):
            add(s, f"bot{k}_{a}", "Bot")
    s = M.W[0]
    add(s, "edge_first", h=0, m=0, s=0)            # 04-30 00:00:00 は突出の週
    add(M.W[1], "edge_last", h=23, m=59, s=59)     # 05-06 23:59:59 も突出の週
    add(M.W[1] + timedelta(days=1), "edge_out", h=0, m=0, s=0)  # 05-07 00:00:00 は外
    for a in range(48):
        add(s + timedelta(days=a % 7), f"s{a}")
    for a in range(149):
        add(s + timedelta(days=a % 7), f"j{a % 10}")
    add(s, None)
    for a in range(50):
        add(s, f"sbot{a}", "Bot")
    for a in range(100):  # 8 月: 100 人 × 3 件
        for dd in (3, 13, 23):
            add(date(2026, 8, dd), f"a{a}")
    return out


def make_releases() -> list[dict]:
    def rel(tag, d, total, prerelease=False, draft=False):
        return {"tag_name": tag, "published_at": ts(d, h=0), "prerelease": prerelease, "draft": draft,
                "assets": [{"name": "x.tar.gz", "download_count": total - 1}, {"name": "y.zip", "download_count": 1}] if total else []}
    return [
        rel("v1", date(2026, 1, 1), 3100), rel("v2", date(2026, 2, 1), 0),
        rel("v3", date(2026, 4, 2), 700), rel("v4", date(2026, 4, 9), 700), rel("v5", date(2026, 4, 16), 700), rel("v6", date(2026, 4, 23), 700),
        rel("v7", date(2026, 4, 30), 2100), rel("v8", date(2026, 5, 7), 0),
        rel("v9", date(2026, 8, 1), 31000), rel("v10", date(2026, 9, 1), 0),
        rel("v7-alpha", date(2026, 5, 1), 10**9, prerelease=True), rel("v7-draft", date(2026, 5, 2), 10**9, draft=True),
    ]


def make_hits() -> list[dict]:
    out, n = [], 0

    def add(d, title, oid=None):
        nonlocal n
        n += 1
        out.append({"objectID": oid or str(n), "title": title, "created_at_i": int(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp())})

    for s, _ in M.BASE_WEEKS:
        for a in range(10):
            add(s + timedelta(days=a % 7), "Show HN: OpenAI Codex CLI tips")
        for a in range(5):
            add(s, "Codexes of the medieval world")
    for a in range(12):
        add(M.W[0] + timedelta(days=a % 7), "codex: a new release")
    add(M.W[0], "codex: a new release", oid=out[-1]["objectID"])  # 重複
    for a in range(10):
        add(date(2026, 1, 10), "Codex and friends")
    for a in range(40):
        add(date(2026, 8, 10), "Why Codex?")
    return out


def main():
    print("== 窓")
    check("突出の週と直前 4 週", (M.W, M.BASE_WEEKS[0], M.BASE_WEEKS[3]),
          ((date(2026, 4, 30), date(2026, 5, 6)), (date(2026, 4, 2), date(2026, 4, 8)), (date(2026, 4, 23), date(2026, 4, 29))))

    issues, rels, hits = make_issues(), make_releases(), make_hits()
    iv = M.stable_intervals(rels, datetime(2026, 9, 21, 12, tzinfo=timezone.utc))
    print("== Q1（週の比）")
    q1 = M.indicators(issues, iv, hits, "codex", "week")
    check("(a) issue: 突出の週", q1["a_issues"]["spike_week"], 200)
    check("(a) issue: 直前 4 週", q1["a_issues"]["base_weeks"], [100, 100, 100, 100])
    check("(a) 比", q1["a_issues"]["ratio"], 2.0)
    check("(b) 初めての人", (q1["b_authors"]["spike_week"], q1["b_authors"]["base_weeks"]), (50, [40, 40, 40, 40]))
    check("(b) 比", q1["b_authors"]["ratio"], 1.25)
    check("(c) Releases", (q1["c_releases"]["spike_week"], q1["c_releases"]["base_weeks"]), (300.0, [100.0] * 4))
    check("(c) 比", q1["c_releases"]["ratio"], 3.0)
    check("(d) HN", (q1["d_hn"]["spike_week"], q1["d_hn"]["base_weeks"]), (12, [10] * 4))
    check("(d) 比", q1["d_hn"]["ratio"], 1.2)
    check("Q1 判定", M.verdict_q1(M.ratios_of(q1)), {"n": 4, "k": 2, "verdict": "保留"})

    print("== Q2（月の比）")
    q2 = M.indicators(issues, iv, hits, "codex", "month")
    check("(a)", (q2["a_issues"]["jan"], q2["a_issues"]["aug"], q2["a_issues"]["ratio"]), (100, 300, 3.0))
    check("(b) 作成者数", (q2["b_authors"]["jan"], q2["b_authors"]["aug"], q2["b_authors"]["ratio"]), (50, 100, 2.0))
    check("(c)", (q2["c_releases"]["jan"], q2["c_releases"]["aug"], q2["c_releases"]["ratio"]), (100.0, 1000.0, 10.0))
    check("(d)", (q2["d_hn"]["jan"], q2["d_hn"]["aug"], q2["d_hn"]["ratio"]), (10, 40, 4.0))
    check("Q2 判定", M.verdict_q2(M.ratios_of(q2)), {"n": 4, "G": 3.5, "verdict": "支持"})

    print("== 判定の境界")
    v1 = lambda *xs: M.verdict_q1({str(i): x for i, x in enumerate(xs)})["verdict"][:6]  # noqa: E731
    check("Q1 4 個中 3 個（1.5 ちょうどを含む）", v1(1.5, 9, 2, 1.49), "人の流入と整")
    check("Q1 4 個中 1 個", v1(1.5, 1, 1, 1.49), "人の流入とは")
    check("Q1 4 個中 2 個", v1(1.5, 2, 1, 1), "保留")
    check("Q1 3 個中 3 個", v1(2, 2, 2, None), "人の流入と整")
    check("Q1 3 個中 2 個", v1(2, 2, 1, None), "保留")
    check("Q1 3 個中 0 個", v1(1, 1, 1, None), "人の流入とは")
    check("Q1 1 個だけ", v1(9, None, None, None), "判定不能")
    v2 = lambda *xs: M.verdict_q2({str(i): x for i, x in enumerate(xs)})["verdict"]  # noqa: E731
    check("Q2 5.88", v2(5.88, 5.88), "支持")
    check("Q2 5.89", v2(5.89, 5.89), "保留")
    check("Q2 11.76", v2(11.76, 11.76), "不支持")
    check("Q2 11.75", v2(11.75, 11.75, None), "保留")
    check("Q2 値が 1 つ", v2(3.0, None, None), "判定不能")

    print("== Releases の按分")
    a, b = datetime(2026, 4, 28, tzinfo=timezone.utc), datetime(2026, 5, 2, tzinfo=timezone.utc)
    check("4 日のうち 2 日が週に重なる: 400 × 2/4 ÷ 7", M.release_rate([(a, b, 400, "x")], M.W), 200 / 7, 1e-9)
    check("重ならなければ値なし", M.release_rate([(a, b, 400, "x")], M.JAN), None)
    check("長さ 0 の区間は入れない", M.release_rate([(a, a, 999, "x"), (a, b, 400, "y")], M.W), 200 / 7, 1e-9)

    print("== Q3 段差の検出（平日 1000 → 2026-02-11 から 2000、週末は半分、0 の日あり、突出の週は置換）")
    daily, d = {}, date(2025, 9, 1)
    while d <= date(2026, 9, 19):
        level = 1000 if d < date(2026, 2, 11) else 2000
        daily[d] = level // 2 if d.weekday() >= 5 else level
        d += timedelta(days=1)
    for z in (date(2025, 12, 3), date(2026, 2, 12), date(2026, 7, 9)):
        daily[z] = 0
    spike = {M.W[0] + timedelta(days=k): 2000.0 for k in range(7)}
    for s_ in spike:
        daily[s_] = 50000
    steps = M.detect_steps(daily, M.Q3_START, date(2026, 9, 19), replace=spike)
    # 同値の最大が 02-07 から続く（前 14 日の中央値が 1000、後 14 日の中央値が 2000 のあいだ）。最も早い日を取る
    check("段差は 1 つ、r = 2.0", [(s_["day"], s_["r"]) for s_ in steps], [(date(2026, 2, 7), 2.0)])
    check("置換しなければ突出を拾う", len(M.detect_steps(daily, M.Q3_START, date(2026, 9, 19))) >= 2, True)
    ev = [{"date": date(2026, 2, 5), "title": "A"}, {"date": date(2026, 2, 8), "title": "B"}, {"date": date(2026, 1, 30), "title": "C"}]
    check("[d−7, d] の項目", [e["title"] for e in M.events_before(date(2026, 2, 7), ev)], ["A"])
    check("偶然に当たる率（3 項目 × 8 日 ÷ 31 日、重なり 3 日）", M.chance_rate(ev, date(2026, 1, 25), date(2026, 2, 24)), 17 / 31, 1e-9)

    print("== Q4 題名の分類（先に合った区分）")
    cases = {
        "Claude Code から Codex CLI に乗り換えた": "乗り換え・比較", "Codex vs Devin": "乗り換え・比較", "VSCode で Codex を使う": "その他",
        "Codex CLI の料金プランまとめ": "料金・制限", "ChatGPT Plus で Codex": "料金・制限", "Codex Pro版を契約した": "料金・制限",
        "Codex でプロンプト（prompt）を書く": "その他", "GPT-5-Codex を試す": "新モデル", "ChatGPT と Codex": "その他", "o3 と Codex": "新モデル",
        "Codex CLI 入門": "使い方・設定", "AGENTS.md の書き方": "使い方・設定",
    }
    for title, want in cases.items():
        check(title, M.classify_title(title), want)
    recs = [{"path": f"/u/articles/{i:02d}", "title": "Codex 入門" if i % 2 else "Claude と比較", "liked_count": i, "published_at": "2026-05-10T00:00:00+09:00"} for i in range(14)]
    recs.append(dict(recs[13]))  # 同じ path の重複
    z = M.zenn_monthly(recs, ["2026-05"])["2026-05"]
    check("月の本数（重複を除く）", z["n_articles"], 14)
    check("上位 10 本の区分", z["top10_categories"], {"使い方・設定": 5, "乗り換え・比較": 5})
    check("題名に claude を含む割合", z["share_title_claude"], 0.5)

    print(f"\n{N - len(FAILS)}/{N} 通過" + ("" if not FAILS else f"、NG: {FAILS}"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()

"""decisions/0003 の事後の参考表（事前登録に無い集計。判定には使わない）。結果を見た後に足したもの。

  python scripts/posthoc_why.py      # docs/data/why_posthoc.json、why_monthly.csv、why_weekly_issues.csv

1. 突出の週を「直前 4 週の平均」ではなく「直前の 1 週（04-23〜04-29）」と比べる（直前 4 週に上向きの傾きがあるため）
2. Q2 の感度: 指標を 1 つずつ除いたときの中央値 G
3. 月別（2026-01〜08）の指数（1 月 = 1）: npm の月別中央値、issue 作成数、作成者数、Releases/日、Hacker News。3 ツール
4. 算術上の分解（仮定つき）: npm の 36.35 倍 = 数え方 2.06 × issue 作成者の伸び × 残り
5. 週次の issue 作成数と作成者数（3 ツール、2026-03-05〜06-03）
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proxy_metrics as M  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
raw = sorted((ROOT / "data" / "proxies").iterdir())[-1]


def slug(s):
    return s.lstrip("@").replace("/", "__")


data = {}
for tool, repo in M.REPOS.items():
    rel = json.loads((raw / "releases" / f"{slug(repo)}.json").read_text(encoding="utf-8"))
    data[tool] = (M.load_jsonl(raw / "issues" / f"{slug(repo)}.jsonl"),
                  M.stable_intervals(rel["releases"], M.parse_ts(rel["fetched_at"])),
                  json.loads((raw / "hn" / f"{tool}.json").read_text(encoding="utf-8"))["hits"])
posthoc = json.loads((ROOT / "docs" / "data" / "posthoc.json").read_text(encoding="utf-8"))
daily = {t: {} for t in M.TOOLS}
with open(ROOT / "docs" / "data" / "daily_downloads.csv", encoding="utf-8") as fp:
    for r in csv.DictReader(fp):
        for t in M.TOOLS:
            if r[t] != "":
                daily[t][date.fromisoformat(r["day"])] = int(r[t])
out: dict = {"note": "事後の参考表。判定には使わない"}

# 1. 直前の 1 週と比べる
issues, iv, hits = data["codex"]
prev = M.BASE_WEEKS[-1]
fns = {"a_issues": lambda p: M.issue_count(issues, p), "b_first_time_authors": lambda p: M.first_time_authors(issues, p),
       "c_releases_per_day": lambda p: M.release_rate(iv, p), "d_hn": lambda p: M.hn_count(hits, "codex", p),
       "npm": lambda p: sum(daily["codex"].get(p[0] + timedelta(days=k), 0) for k in range(7))}
out["spike_vs_previous_week"] = {k: {"previous_week": fn(prev), "spike_week": fn(M.W), "ratio": M.ratio(fn(M.W), fn(prev)),
                                      "week_before_previous": fn(M.BASE_WEEKS[-2]), "previous_vs_before": M.ratio(fn(prev), fn(M.BASE_WEEKS[-2]))}
                                 for k, fn in fns.items()}

# 2. Q2 の感度
why = json.loads((ROOT / "docs" / "data" / "why_summary.json").read_text(encoding="utf-8"))
ratios = {k: v["ratio"] for k, v in why["Q2"]["codex"]["indicators"].items() if v and v["ratio"] is not None}
out["q2_sensitivity"] = {"all": {"G": median(ratios.values()), "verdict": M.verdict_q2(ratios)["verdict"]}}
for drop in ratios:
    rest = {k: v for k, v in ratios.items() if k != drop}
    out["q2_sensitivity"][f"without_{drop}"] = {"G": median(rest.values()), "verdict": M.verdict_q2(rest)["verdict"]}

# 3. 月別の指数
months = [(date(2026, m, 1), (date(2026, m + 1, 1) - timedelta(days=1))) for m in range(1, 9)]
rows, monthly = [], {}
for tool in M.TOOLS:
    issues_t, iv_t, hits_t = data[tool]
    spikes = {date.fromisoformat(x["day"]) for x in posthoc["spikes"]["per_tool"][tool]}
    monthly[tool] = []
    for p in months:
        vals = [v for d, v in daily[tool].items() if p[0] <= d <= p[1] and v > 0]
        rec = {"month": p[0].isoformat()[:7], "npm_median": median(vals), "issues": M.issue_count(issues_t, p), "authors": M.authors(issues_t, p),
               "releases_per_day": M.release_rate(iv_t, p), "hn": M.hn_count(hits_t, tool, p)}
        monthly[tool].append(rec)
        rows.append([tool, rec["month"], rec["npm_median"], rec["issues"], rec["authors"],
                     round(rec["releases_per_day"], 1) if rec["releases_per_day"] is not None else "", rec["hn"]])
out["monthly"] = monthly
with open(ROOT / "docs" / "data" / "why_monthly.csv", "w", encoding="utf-8", newline="") as fp:
    w = csv.writer(fp, lineterminator="\n")
    w.writerow(["tool", "month", "npm_daily_median_nonzero", "issues_created", "issue_authors", "releases_downloads_per_day", "hn_stories"])
    w.writerows(rows)

# 4. 算術上の分解（codex、2026-01 → 08）
c = monthly["codex"]
npm_ratio = c[-1]["npm_median"] / c[0]["npm_median"]
author_ratio = c[-1]["authors"] / c[0]["authors"]
counting = 1 / (1 - 0.5147)
out["decomposition_codex"] = {"npm_ratio": npm_ratio, "counting_factor": counting, "issue_author_ratio": author_ratio,
                              "residual": npm_ratio / counting / author_ratio,
                              "note": "数え方の係数は直近 7 日の s = 0.5147 が 2026-08 にも当てはまると仮定。issue 作成者を「人」の代理に置いた算術で、因果の分解ではない"}

# 5. 週次の issue（3 ツール）
weeks, s = [], date(2026, 3, 5)
while s <= date(2026, 5, 28):
    weeks.append((s, s + timedelta(days=6)))
    s += timedelta(days=7)
wrows = [[p[0].isoformat()] + [x for t in M.TOOLS for x in (M.issue_count(data[t][0], p), M.authors(data[t][0], p))] for p in weeks]
with open(ROOT / "docs" / "data" / "why_weekly_issues.csv", "w", encoding="utf-8", newline="") as fp:
    w = csv.writer(fp, lineterminator="\n")
    w.writerow(["week_start_thu"] + [f"{t}_{k}" for t in M.TOOLS for k in ("issues", "authors")])
    w.writerows(wrows)
out["weekly_issues"] = {"header": ["week"] + [f"{t}_{k}" for t in M.TOOLS for k in ("issues", "authors")], "rows": wrows}

(ROOT / "docs" / "data" / "why_posthoc.json").write_text(json.dumps(M.to_jsonable(out), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

print("[1] 突出の週 ÷ 直前の 1 週（かっこ内は 直前の週 ÷ その前の週）")
for k, v in out["spike_vs_previous_week"].items():
    print(f"  {k}: {v['previous_week']:,.0f} → {v['spike_week']:,.0f}  比 {v['ratio']:.2f}（{v['previous_vs_before']:.2f}）")
print("[2] Q2 の感度:", {k: (round(v["G"], 2), v["verdict"]) for k, v in out["q2_sensitivity"].items()})
print("[3] 月別（1 月 = 1 の指数: npm / issue / 作成者 / Releases / HN）")
for tool in M.TOOLS:
    b = monthly[tool][0]
    for rec in monthly[tool]:
        idx = [rec[k] / b[k] if b[k] else None for k in ("npm_median", "issues", "authors", "releases_per_day", "hn")]
        print(f"  {tool} {rec['month']}: npm {rec['npm_median']:>11,.0f} issue {rec['issues']:>6,} 作成者 {rec['authors']:>6,} Releases {rec['releases_per_day'] or 0:>9,.0f} HN {rec['hn']:>4} | 指数 "
              + " / ".join("―" if x is None else f"{x:.2f}" for x in idx))
print("[4] 分解:", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in out["decomposition_codex"].items() if k != "note"})
print("[5] 週次の issue・作成者（codex / claude / gemini）")
for r in wrows:
    print("  ", r)

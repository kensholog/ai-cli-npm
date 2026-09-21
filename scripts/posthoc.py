"""事後の参考表（事前登録に無い集計）。判定には使わない。結果を見た後に足したもの。

  python scripts/posthoc.py        # docs/data/posthoc.json に書き、要点を表示する

1. 0 の日（日付は返るが値が 0 の日）の一覧と、各窓に入る数
2. P2 の感度: 0 の日を除く / 前後 14 日の平日の中央値で割ってトレンドを除く / 窓の前半・後半
3. P1b の大きさ: 二重計上だけなら最大 2 倍、という上限と比べる。月別の中央値
4. P3 に formula `codex` を足した場合（homebrew-core の履歴で OpenAI の Codex と確認。2025-10-17 に cask へ移行）
5. Claude Code のプラットフォーム別 8 パッケージの合計 ÷ 本体、Codex のプラットフォーム版 ÷ 安定版
6. 突出した日（前後 14 日の 0 でない日の中央値の 5 倍を超える日）と、それを除いた期間合計・順位
"""
import json
import sys
from datetime import timedelta
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metrics as M  # noqa: E402
import rawlayout as L  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
D1 = timedelta(days=1)


def p2_variant(daily, rel, win, keep=lambda d, v: True, value=lambda d, v: v):
    r, n = [], []
    for d in M.days(win):
        if d.weekday() >= 5 or not keep(d, daily[d]):
            continue
        (r if (d in rel or d - D1 in rel) else n).append(value(d, daily[d]))
    return {"n_release": len(r), "n_other": len(n), "ratio": M.ratio(median(r) if r else None, median(n) if n else None)}


def main() -> None:
    raw_dir = sorted((ROOT / "data" / "raw").iterdir())[-1]
    r = M.analyze(raw_dir)
    raw = M.Raw(raw_dir)
    dailies, rels, last = r["_dailies"], r["_release_days"], r["last_day"]
    out: dict = {"note": "事後の参考表。判定には使わない", "fetch_date_utc": r["fetch_date_utc"]}

    # 1. 0 の日
    wins = {"P1b 前": M.P1B_BEFORE, "P1b 後": M.P1B_AFTER, "直近 180 日": L.window(last, 180), "直近 30 日": L.window(last, 30),
            "記述 c 前": M.step_windows(M.E_CLAUDE_SPLIT)[0], "記述 c 後": M.step_windows(M.E_CLAUDE_SPLIT)[1]}
    zeros = {}
    for t in L.TOOLS:
        first = r["A"]["per_tool"][t]["first_nonzero"]
        zeros[t] = [d for d in M.days((first, last)) if dailies[t][d] == 0]
    common = sorted(set(zeros["claude"]) & set(zeros["codex"]) & set(zeros["gemini"]))
    plat_zero = {}
    for e in raw.entries("npm_range_platform"):
        daily = M.load_daily(raw, "npm_range_platform", e["package"])
        nz = [d for d in sorted(daily) if daily[d] > 0]
        plat_zero[e["package"]] = [d for d in M.days((nz[0], last)) if daily[d] == 0]
    out["zero_days"] = {
        "per_tool": zeros, "common_to_all_three": common,
        "in_windows": {name: {t: sum(1 for d in zeros[t] if w[0] <= d <= w[1]) for t in L.TOOLS} for name, w in wins.items()},
        "weekday_zero_in_180d": {t: sum(1 for d in zeros[t] if wins["直近 180 日"][0] <= d and d.weekday() < 5) for t in L.TOOLS},
        "platform_packages_zero_days": plat_zero,
    }

    # 2. P2 の感度
    w180 = L.window(last, 180)
    half = (w180[0], w180[0] + timedelta(days=89)), (w180[0] + timedelta(days=90), w180[1])
    out["p2_sensitivity"] = {}
    for t in L.TOOLS:
        daily, rel = dailies[t], rels[t]

        def baseline(d, daily=daily):
            near = [daily[x] for x in M.days((d - timedelta(days=14), min(d + timedelta(days=14), last)))
                    if x.weekday() < 5 and daily.get(x, 0) > 0]
            return median(near)

        nonzero = lambda d, v: v > 0  # noqa: E731
        out["p2_sensitivity"][t] = {
            "事前登録どおり": {k: r["P2"][t][k] for k in ("n_release", "n_other", "ratio")},
            "0 の日を除く": p2_variant(daily, rel, w180, keep=nonzero),
            "0 の日を除き、前後 14 日の平日の中央値で割る": p2_variant(daily, rel, w180, keep=nonzero, value=lambda d, v: v / baseline(d)),
            "前半 90 日（0 の日を除く）": p2_variant(daily, rel, half[0], keep=nonzero),
            "後半 90 日（0 の日を除く）": p2_variant(daily, rel, half[1], keep=nonzero),
            "release_days_by_month": {},
        }
        for d in M.days(w180):
            if d in rel:
                k = f"{d:%Y-%m}"
                out["p2_sensitivity"][t]["release_days_by_month"][k] = out["p2_sensitivity"][t]["release_days_by_month"].get(k, 0) + 1

    # 3. P1b の大きさと月別の中央値
    p = r["P1b"]
    out["p1b_magnitude"] = {
        "codex_ratio": p["per_tool"]["codex"]["ratio"], "others_mean": p["others_mean"], "did": p["did"],
        "did_if_codex_after_halved": p["per_tool"]["codex"]["ratio"] / 2 / p["others_mean"],
        "note": "二重計上だけなら Codex の比は最大 2 倍。後の中央値を半分にしても差の差が 1 を超えるなら、数え方以外の増加がある",
    }
    months = sorted({f"{d:%Y-%m}" for d in M.days((r["A"]["per_tool"]["gemini"]["pub_date"], last))})
    out["monthly_median_nonzero"] = {
        t: {m: median([v for d, v in dailies[t].items() if f"{d:%Y-%m}" == m and v > 0 and d <= last] or [0]) for m in months}
        for t in L.TOOLS}

    # 4. P3 に formula codex を足した場合
    out["p3_with_formula_codex"] = {}
    for period, x in r["P3"]["periods"].items():
        body = raw.load_one("brew_analytics", category="install", period=period)
        extra = M.brew_count(body, "codex") or 0
        brew = dict(x["brew"])
        brew["codex"] += extra
        out["p3_with_formula_codex"][period] = {"formula_codex_install": extra, "brew": brew, "brew_rank": M.rank(brew),
                                                "npm_rank": x["npm_rank"], "same_order": M.rank(brew) == x["npm_rank"],
                                                "npm_ratio_codex_to_claude": x["npm"]["codex"] / x["npm"]["claude"],
                                                "brew_ratio_codex_to_claude": brew["codex"] / brew["claude"],
                                                "npm_ratio_gemini_to_claude": x["npm"]["gemini"] / x["npm"]["claude"],
                                                "brew_ratio_gemini_to_claude": brew["gemini"] / brew["claude"]}

    # 5. プラットフォーム別の合計 ÷ 本体
    a = r["desc"]["a_claude_platform_share"]
    out["platform_vs_main"] = {
        "claude_platform_total_30d": a["total"], "claude_main_30d": r["P3"]["periods"]["30d"]["npm"]["claude"],
        "claude_ratio": a["total"] / r["P3"]["periods"]["30d"]["npm"]["claude"],
        "codex_platform_lastweek": r["P1a"]["platform_total"], "codex_stable_lastweek": r["P1a"]["stable_total"],
        "codex_ratio": r["P1a"]["platform_total"] / r["P1a"]["stable_total"],
        "codex_platform_linux_share": (r["P1a"]["by_suffix"]["-linux-x64"] + r["P1a"]["by_suffix"]["-linux-arm64"]) / r["P1a"]["platform_total"],
        "codex_half_of_total_30d": r["P3"]["periods"]["30d"]["npm"]["codex"] * (1 - r["P1a"]["s"]),
    }

    # 6. 突出した日
    spikes = {}
    for t in L.TOOLS:
        first = r["A"]["per_tool"][t]["first_nonzero"]
        rows = []
        for d in M.days((first + timedelta(days=14), last)):
            near = [dailies[t][x] for x in M.days((d - timedelta(days=14), min(d + timedelta(days=14), last)))
                    if x != d and dailies[t].get(x, 0) > 0]
            base = median(near)
            if dailies[t][d] > 5 * base:
                rows.append({"day": d, "downloads": dailies[t][d], "baseline": base, "ratio": dailies[t][d] / base})
        spikes[t] = rows
    out["spikes"] = {"rule": "その日の値 > 前後 14 日（その日を除く、0 の日を除く）の中央値 × 5。公開から 14 日以内は対象外", "per_tool": spikes, "totals": {}}
    for period, n in M.NPM_DAYS.items():
        w = L.window(last, n)
        full = {t: sum(dailies[t].get(d, 0) for d in M.days(w)) for t in L.TOOLS}
        spike_sum = {t: sum(x["downloads"] for x in spikes[t] if w[0] <= x["day"] <= w[1]) for t in L.TOOLS}
        # 突出した日は、その日の baseline（前後の中央値）に置き換える
        adj = {t: full[t] - spike_sum[t] + sum(x["baseline"] for x in spikes[t] if w[0] <= x["day"] <= w[1]) for t in L.TOOLS}
        out["spikes"]["totals"][period] = {"full": full, "spike_sum": spike_sum, "spike_share": {t: spike_sum[t] / full[t] for t in L.TOOLS},
                                           "adjusted": adj, "rank_full": M.rank(full), "rank_adjusted": M.rank(adj)}

    (ROOT / "docs" / "data" / "posthoc.json").write_text(json.dumps(M.to_jsonable(out), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(M.to_jsonable(out["spikes"]), ensure_ascii=False, indent=1))
    print("月別の中央値（0 の日を除く）")
    for m in months:
        print(" ", m, " / ".join(f"{t} {out['monthly_median_nonzero'][t][m]:,.0f}" for t in L.TOOLS))


if __name__ == "__main__":
    main()

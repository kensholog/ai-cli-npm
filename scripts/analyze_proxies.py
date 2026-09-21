"""data/proxies/<取得日>/ を集計して、decisions/0003 の Q1・Q2 の判定と Q3・Q4・突出の追加確認の記述を出す。

  python scripts/analyze_proxies.py            # data/proxies/ の最新。docs/data/why_*.{json,csv} に書く

定義・窓・閾値は docs/decisions/0003 のとおり（実装は proxy_metrics.py）。0003 に無い集計はここに足さない。
変更履歴の項目（Q3）は data/proxies/<取得日>/changelog_events.json（[{date, title, label}]）があれば使う。
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proxy_metrics as M  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
ZENN = ROOT.parent / "zenn-trend" / "data" / "topics"
NAME = {"codex": "Codex CLI", "claude": "Claude Code", "gemini": "Gemini CLI"}
LABEL = {"a_issues": "(a) issue 作成数", "b_authors": "(b) 作成者", "c_releases": "(c) Releases/日", "d_hn": "(d) HN 投稿数"}
LAST_DAY = date(2026, 9, 19)


def slug(s):
    return s.lstrip("@").replace("/", "__")


def f(x, nd=2):
    return "―" if x is None else f"{x:,.{nd}f}" if isinstance(x, float) else f"{x:,}"


def main() -> None:
    raw = sorted((ROOT / "data" / "proxies").iterdir())[-1]
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    out: dict = {"fetch_date_utc": raw.name, "n_requests": len(manifest["requests"]),
                 "npm_known": {"week_ratio": M.NPM_WEEK_RATIO, "month_ratio_adjusted": M.NPM_MONTH_RATIO_ADJ}}

    data = {}
    for tool, repo in M.REPOS.items():
        ip, rp, hp = raw / "issues" / f"{slug(repo)}.jsonl", raw / "releases" / f"{slug(repo)}.json", raw / "hn" / f"{tool}.json"
        issues = M.load_jsonl(ip) if ip.exists() and json.loads((raw / "issues" / f"{slug(repo)}.state.json").read_text())["done"] else None
        rel = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else None
        hits = json.loads(hp.read_text(encoding="utf-8"))["hits"] if hp.exists() else None
        iv = M.stable_intervals(rel["releases"], M.parse_ts(rel["fetched_at"])) if rel else None
        data[tool] = (issues, rel, iv, hits)

    # D: 到達
    d_check = {}
    for tool, (issues, rel, iv, hits) in data.items():
        ts = sorted(i["createdAt"] for i in issues) if issues else []
        d_check[tool] = {
            "issues_first": ts[0][:10] if ts else None, "issues_last": ts[-1][:10] if ts else None,
            "issues_ok": bool(ts) and ts[-1][:10] >= LAST_DAY.isoformat(),
            "stable_first": iv[0][0].date() if iv else None, "stable_last": iv[-1][0].date() if iv else None, "n_stable": len(iv) if iv else 0,
            "releases_ok": bool(iv) and iv[0][0].date() <= date(2026, 1, 1),
            "hn_ok": hits is not None,
        }
    out["D"] = d_check
    print("[D] 到達")
    for tool, x in d_check.items():
        print(f"  {NAME[tool]}: issue {x['issues_first']}〜{x['issues_last']}（{'可' if x['issues_ok'] else '不可'}） / 安定版のリリース {x['n_stable']} 本 "
              f"{x['stable_first']}〜{x['stable_last']}（{'可' if x['releases_ok'] else '不可'}） / HN {'可' if x['hn_ok'] else '不可'}")

    def usable(tool):
        issues, rel, iv, hits = data[tool]
        x = d_check[tool]
        return (issues if x["issues_ok"] else None, iv if x["releases_ok"] else None, hits)

    # Q1（codex）と、同じ表を他の 2 つにも（記述）
    out["Q1"] = {}
    print(f"\n[Q1] 突出の週 {M.W[0]}〜{M.W[1]} ÷ 直前 4 週の平均（1.5 以上を数える。npm は {M.NPM_WEEK_RATIO}）")
    for tool in M.TOOLS:
        ind = M.indicators(*usable(tool), tool, "week")
        out["Q1"][tool] = {"indicators": ind, **(M.verdict_q1(M.ratios_of(ind)) if tool == "codex" else {})}
        print(f"  {NAME[tool]}")
        for k, v in ind.items():
            if v:
                print(f"    {LABEL[k]}: 突出の週 {f(v['spike_week'])} / 直前 4 週 {[round(x, 1) if isinstance(x, float) else x for x in v['base_weeks']]} / 比 {f(v['ratio'])}")
    q1 = out["Q1"]["codex"]
    print(f"  → Codex CLI: {q1['n']} 個中 {q1['k']} 個が 1.5 以上 → {q1['verdict']}")

    out["Q2"] = {}
    print(f"\n[Q2] 2026-08 ÷ 2026-01（npm は数え方を除いて {M.NPM_MONTH_RATIO_ADJ}。G が {M.Q2_SUPPORT} 以下で支持、{M.Q2_REJECT} 以上で不支持）")
    for tool in M.TOOLS:
        ind = M.indicators(*usable(tool), tool, "month")
        out["Q2"][tool] = {"indicators": ind, **M.verdict_q2(M.ratios_of(ind))}
        print(f"  {NAME[tool]}: " + " / ".join(f"{LABEL[k]} {f(v['jan'])} → {f(v['aug'])}（{f(v['ratio'])}）" for k, v in ind.items() if v)
              + f" → 中央値 G = {f(out['Q2'][tool]['G'])}" + (f" → {out['Q2'][tool]['verdict']}" if tool == "codex" else "（記述）"))

    # 週次の系列（図と確認用。木曜はじまりで W に合わせる）
    issues_c, _, iv_c, hits_c = data["codex"]
    daily = {t: {} for t in M.TOOLS}
    with open(ROOT / "docs" / "data" / "daily_downloads.csv", encoding="utf-8") as fp:
        for r in csv.DictReader(fp):
            for t in M.TOOLS:
                if r[t] != "":
                    daily[t][date.fromisoformat(r["day"])] = int(r[t])
    weeks, s = [], M.W[0] - timedelta(days=7 * 17)
    while s + timedelta(days=6) <= LAST_DAY:
        weeks.append((s, s + timedelta(days=6)))
        s += timedelta(days=7)
    rows = []
    for p in weeks:
        rows.append([p[0].isoformat(), sum(daily["codex"].get(p[0] + timedelta(days=k), 0) for k in range(7)),
                     M.issue_count(issues_c, p) if issues_c else "", M.first_time_authors(issues_c, p) if issues_c else "",
                     round(M.release_rate(iv_c, p) or 0, 1) if iv_c else "", M.hn_count(hits_c, "codex", p) if hits_c else ""])
    with open(ROOT / "docs" / "data" / "why_codex_weekly.csv", "w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp, lineterminator="\n")
        w.writerow(["week_start_thu", "npm_downloads", "issues_created", "first_time_issue_authors", "releases_downloads_per_day", "hn_stories"])
        w.writerows(rows)

    # Q3
    posthoc = json.loads((ROOT / "docs" / "data" / "posthoc.json").read_text(encoding="utf-8"))
    ev_path = raw / "changelog_events.json"
    events = [{**e, "date": date.fromisoformat(e["date"])} for e in json.loads(ev_path.read_text(encoding="utf-8"))] if ev_path.exists() else []
    out["Q3"] = {"n_changelog_events": len(events),
                 "chance_rate": M.chance_rate(events, M.Q3_START, LAST_DAY) if events else None, "steps": {}}
    print(f"\n[Q3] npm の段差（r ≥ {M.Q3_MIN_R}）と直前 7 日の出来事。変更履歴 {len(events)} 項目、偶然に当たる率 {f(out['Q3']['chance_rate'])}")
    for tool in M.TOOLS:
        replace = {date.fromisoformat(x["day"]): x["baseline"] for x in posthoc["spikes"]["per_tool"][tool]}
        steps = M.detect_steps(daily[tool], M.Q3_START, LAST_DAY, replace)
        iv = data[tool][2] or []
        rel_by_tag = {r["tag_name"]: r for r in (data[tool][1] or {"releases": []})["releases"]}
        for st in steps:
            st["changelog"] = [{"date": e["date"], "title": e["title"], "label": e.get("label")} for e in M.events_before(st["day"], events)] if tool == "codex" else []
            st["changelog_after_7d"] = [{"date": e["date"], "title": e["title"], "label": e.get("label")} for e in events
                                        if st["day"] < e["date"] <= st["day"] + timedelta(days=7)] if tool == "codex" else []
            st["stable_releases"] = [{"tag": tag, "published": a.date(), "name": rel_by_tag[tag].get("name")}
                                     for a, _, _, tag in iv if st["day"] - timedelta(days=7) <= a.date() <= st["day"] + timedelta(days=7)]
        out["Q3"]["steps"][tool] = steps
        print(f"  {NAME[tool]}: " + ("段差なし" if not steps else ""))
        for st in steps:
            print(f"    {st['day']} r = {st['r']:.2f} / 変更履歴 [d−7, d]: {[(str(e['date']), e['title']) for e in st['changelog']]} / (d, d+7]: {[(str(e['date']), e['title']) for e in st['changelog_after_7d']]}"
                  f" / 安定版 ±7 日: {[(r['tag'], str(r['published'])) for r in st['stable_releases']]}")

    # Q4
    recs = []
    for name in ("codex", "codexcli"):
        p = ZENN / f"{name}.jsonl"
        if p.exists():
            recs += M.load_jsonl(p)
    months = [f"{y}-{m:02d}" for y, m in [(2025, 9), (2025, 10), (2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 9)]]
    out["Q4"] = M.zenn_monthly(recs, months) if recs else None
    if recs:
        print("\n[Q4] Zenn の codex・codexcli（月別。上位 10 本の区分）")
        for m, x in out["Q4"].items():
            print(f"  {m}: {x['n_articles']} 本、題名に claude {f((x['share_title_claude'] or 0) * 100, 1)}% / {x['top10_categories']}")

    # 突出の追加確認
    sp: dict = {"npm_related": {}}
    for pkg in ("@openai/codex-sdk", "openai", "@openai/agents"):
        p = raw / "npm_related" / f"{slug(pkg)}.json"
        if p.exists():
            body = json.loads(p.read_text(encoding="utf-8"))
            if body["status"] == 200:
                dd = {date.fromisoformat(r["day"]): r["downloads"] for r in body["body"]["downloads"]}
                sp["npm_related"][pkg] = M.week_ratio(lambda pr: sum(dd.get(pr[0] + timedelta(days=k), 0) for k in range(7)))
            else:
                sp["npm_related"][pkg] = {"status": body["status"]}
    reg = json.loads((sorted((ROOT / "data" / "raw").iterdir())[-1] / "registry" / "openai__codex.json").read_text(encoding="utf-8"))
    sp["versions_published"] = sorted((t[:16], v) for v, t in reg["time"].items() if "2026-04-25" <= t[:10] <= "2026-05-07" and "-" not in v)
    rel_c = (data["codex"][1] or {"releases": []})["releases"]
    sp["release_note_lines"] = [{"tag": r["tag_name"], "published": r["published_at"][:10], "line": line.strip()[:200]}
                                for r in rel_c if not r["prerelease"] and not r["draft"] and "2026-04-20" <= (r["published_at"] or "")[:10] <= "2026-05-10"
                                for line in (r.get("body") or "").splitlines() if M.SPIKE_NOTE_RE.search(line)]
    if issues_c:
        hit = [i for i in M.human_issues(issues_c) if "2026-04-28" <= i["createdAt"][:10] <= "2026-05-10" and M.SPIKE_ISSUE_RE.search(i["title"] or "")]
        sp["issues_matching"] = {"n": len(hit), "titles": [(i["createdAt"][:10], i["number"], i["title"][:120]) for i in hit[:60]]}
    out["spike_checks"] = sp
    print("\n[突出の追加確認]")
    for pkg, x in sp["npm_related"].items():
        print(f"  {pkg}: " + (f"突出の週 {f(x['spike_week'])} / 直前 4 週の平均 {f(x['base_mean'])} / 比 {f(x['ratio'])}" if "ratio" in x else f"取れない（{x['status']}）"))
    print(f"  04-25〜05-07 に公開された安定版: {sp['versions_published']}")
    print(f"  リリースノートの該当行: {len(sp['release_note_lines'])} 行")
    for x in sp["release_note_lines"][:40]:
        print(f"    {x['published']} {x['tag']}: {x['line']}")
    if "issues_matching" in sp:
        print(f"  issue（04-28〜05-10、題名に npm|install|update|download）: {sp['issues_matching']['n']} 件")
        for t in sp["issues_matching"]["titles"][:40]:
            print(f"    {t[0]} #{t[1]} {t[2]}")

    (ROOT / "docs" / "data" / "why_summary.json").write_text(json.dumps(M.to_jsonable(out), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

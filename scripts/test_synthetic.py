"""答えの分かっている合成データで metrics.py を検証する（実データに当てる前に通す）。

fetch.py と同じリクエスト計画（rawlayout）から、API と同じ形の JSON を一時フォルダに作り、
metrics.analyze() の結果を、手計算した期待値と突き合わせる。期待値の根拠は各 check の上のコメント。

  python scripts/test_synthetic.py

合成データの作り（取得日 2026-09-21、集計の最終日 09-19（土）、直近 180 日 = 03-24（火）〜09-19）:
- 平日の水準  codex: E（2026-02-11）より前 1000、以後 2000 / claude: 1000 → 1100 → 2026-04-13 から 550 / gemini: 1000 → 900
- 週末は水準の codex 0.3 倍・claude 0.5 倍・gemini 0.25 倍
- 移行期間（E〜E+13 の codex、04-13〜04-26 の claude）は 99999 / 77777（窓から外れていなければ中央値が壊れる）
- codex の 2026-01-20 は外れ値 50000（平均を使っていれば P1b が壊れる）
- 安定版  codex: 毎週火曜 ＋ E ＋ 2026-06-07（日）12:00 UTC ＋ 2026-07-10（金）23:30 UTC ＋ 2026-05-04（月。time にだけある取り下げ版）
          claude: 毎日 / gemini: 毎週木曜。codex には毎日の alpha とプラットフォーム版（どちらも安定版ではない）
- 「リリース日か前日がリリース日」の平日は codex 1.5 倍、gemini 1.1 倍
"""
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metrics as M  # noqa: E402
import rawlayout as L  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

PUB = {"claude": date(2025, 2, 24), "codex": date(2025, 4, 16), "gemini": date(2025, 6, 25)}
WEEKEND = {"claude": 0.5, "codex": 0.3, "gemini": 0.25}
BUMP = {"claude": 1.0, "codex": 1.5, "gemini": 1.1}
E, SPLIT = date(2026, 2, 11), date(2026, 4, 13)
CODEX_EXTRA = {E: "T18:00:00.000Z", date(2026, 6, 7): "T12:00:00.000Z", date(2026, 7, 10): "T23:30:00.000Z"}
CODEX_UNPUBLISHED = date(2026, 5, 4)
PLATFORM_PER_DAY = {"linux-x64": 100, "linux-arm64": 20, "linux-x64-musl": 10, "linux-arm64-musl": 5,
                    "darwin-arm64": 50, "darwin-x64": 5, "win32-x64": 9, "win32-arm64": 1}
CODEX_VERSIONS = {
    "0.155.0": 500, "0.155.0-linux-x64": 200, "0.155.0-darwin-arm64": 150, "0.155.0-win32-x64": 50,
    "0.155.0-darwin-x64": 20, "0.155.0-linux-arm64": 20, "0.155.0-win32-arm64": 10,
    "0.156.0-alpha.1": 30, "0.156.0-alpha.1-linux-x64": 10, "0.98.0": 10,
    "0.1.0-linux-x64-musl": 40,  # 0001 の 6 つの接尾辞に当たらないので、プラットフォーム版に数えない
}
D1 = timedelta(days=1)


def release_days(tool: str, end: date) -> set[date]:
    out, d = {PUB[tool]}, PUB[tool]
    while d <= end:
        if tool == "claude" or (tool == "codex" and d.weekday() == 1) or (tool == "gemini" and d.weekday() == 3):
            out.add(d)
        d += D1
    if tool == "codex":
        out |= set(CODEX_EXTRA) | {CODEX_UNPUBLISHED}
    return out


def level(tool: str, d: date) -> int:
    if tool == "codex":
        return 1000 if d < E else 2000
    if tool == "claude":
        return 1000 if d < E else 1100 if d < SPLIT else 550
    return 1000 if d < E else 900


def value(tool: str, d: date, rel: set[date]) -> int:
    if d < PUB[tool]:
        return 0
    if tool == "codex" and E <= d <= E + 13 * D1:
        return 99999
    if tool == "claude" and SPLIT <= d <= SPLIT + 13 * D1:
        return 77777
    if tool == "codex" and d == date(2026, 1, 20):
        return 50000
    if d.weekday() >= 5:
        return int(level(tool, d) * WEEKEND[tool])
    if d in rel or d - D1 in rel:
        return int(round(level(tool, d) * BUMP[tool]))
    return level(tool, d)


def registry(tool: str, end: date) -> dict:
    pkg = L.PACKAGES[tool]
    times, versions = {"created": f"{PUB[tool]}T00:00:00.000Z", "modified": f"{end}T00:00:00.000Z"}, {}
    for n, d in enumerate(sorted(release_days(tool, end)), start=1):
        v = f"0.{n}.0"
        times[v] = f"{d}{CODEX_EXTRA.get(d, 'T20:00:00.000Z') if tool == 'codex' else 'T20:00:00.000Z'}"
        if tool == "codex" and d == CODEX_UNPUBLISHED:
            continue  # time にだけ残る取り下げ版
        opt = {}
        if tool == "codex" and d >= E:
            opt = {"@openai/codex-linux-x64": f"npm:@openai/codex@{v}-linux-x64"}
            times[f"{v}-linux-x64"] = times[v]
            versions[f"{v}-linux-x64"] = {"version": f"{v}-linux-x64"}
        if tool == "claude":
            opt = ({L.CLAUDE_PLATFORM_PREFIX + k: v for k in PLATFORM_PER_DAY} if d >= SPLIT
                   else {"@img/sharp-linux-x64": "^0.33.5"})
        versions[v] = {"version": v, "optionalDependencies": opt}
        latest = v
    if tool != "claude":  # 毎日のプレリリース（安定版ではない）
        d, i = PUB[tool], 0
        while d <= end:
            i += 1
            pv = f"9.9.9-alpha.{i}" if tool == "codex" else f"9.9.9-nightly.{d:%Y%m%d}.abc{i}"
            times[pv] = f"{d}T00:00:00.000Z"
            versions[pv] = {"version": pv}
            d += D1
    return {"name": pkg, "dist-tags": {"latest": latest}, "versions": versions, "time": times}


def brew_items(key: str, rows: dict[str, int]) -> list[dict]:
    rows = {"zz-other": 1234567, **rows}
    return [{"number": i, key: k, "count": f"{v:,}", "percent": "1.00"} for i, (k, v) in enumerate(rows.items(), 1)]


BREW = {
    ("install", "30d"): {"gemini-cli": 3000, "codex": 500},
    ("install", "90d"): {"gemini-cli": 9000, "codex": 1500},
    ("install", "365d"): {"gemini-cli": 30000, "codex": 5000},
    ("install-on-request", "30d"): {"gemini-cli": 2900, "codex": 450},
    ("install-on-request", "90d"): {"gemini-cli": 8700, "codex": 1350},
    ("install-on-request", "365d"): {"gemini-cli": 29000, "codex": 4500},
    ("cask-install", "30d"): {"claude-code": 5000, "claude-code@latest": 1000, "codex": 7000},
    ("cask-install", "90d"): {"claude-code": 15000, "claude-code@latest": 3000, "codex": 21000},
    ("cask-install", "365d"): {"claude-code": 80000, "codex": 70000},  # claude-code@latest は一覧に無い
}


def build(raw: Path, fetch_date: date, variant: str = "base") -> None:
    end = fetch_date - D1
    rel = {t: release_days(t, end) for t in L.TOOLS}
    tool_of = {p: t for t, p in L.PACKAGES.items()}
    regs = {t: registry(t, end) for t in L.TOOLS}
    if variant == "missing_time":
        regs["claude"]["versions"]["99.0.0"] = {"version": "99.0.0"}
    w30 = L.window(L.last_day(fetch_date), 30)
    entries = []
    plan = L.plan_stage1() + L.plan_stage2(fetch_date, L.claude_platform_packages(regs["claude"]))
    for spec in plan:
        kind, status, body = spec["kind"], 200, None
        if kind == "registry":
            body = regs[tool_of[spec["package"]]]
        elif kind == "npm_range":
            t = tool_of[spec["package"]]
            ds = M.days((date.fromisoformat(spec["start"]), date.fromisoformat(spec["end"])))
            if variant == "missing_day" and t == "codex":
                ds = [d for d in ds if d != date(2026, 3, 1)]
            body = {"start": spec["start"], "end": spec["end"], "package": spec["package"],
                    "downloads": [{"downloads": value(t, d, rel[t]), "day": d.isoformat()} for d in ds]}
        elif kind == "npm_point":
            t = tool_of[spec["package"]]
            total = sum(value(t, d, rel[t]) for d in M.days(w30))
            if variant == "b_fail" and t == "gemini":
                total = int(total * 1.02)
            body = {"downloads": total, "start": spec["start"], "end": spec["end"], "package": spec["package"]}
        elif kind == "npm_versions":
            if variant == "no_versions":
                status = 404
            body = {"package": spec["package"],
                    "downloads": CODEX_VERSIONS if spec["package"] == L.PACKAGES["codex"] else {"1.0.0": 700, "1.0.1-beta.1": 300}}
        elif kind == "npm_point_lastweek":
            body = {"downloads": 1040 if spec["package"] == L.PACKAGES["codex"] else 1000,
                    "start": "2026-09-14", "end": "2026-09-20", "package": spec["package"]}
        elif kind == "npm_range_platform":
            per_day = PLATFORM_PER_DAY[spec["package"][len(L.CLAUDE_PLATFORM_PREFIX):]]
            ds = M.days((date.fromisoformat(spec["start"]), date.fromisoformat(spec["end"])))
            body = {"start": spec["start"], "end": spec["end"], "package": spec["package"],
                    "downloads": [{"downloads": per_day if d >= SPLIT else 0, "day": d.isoformat()} for d in ds]}
        elif kind == "brew_analytics":
            if variant == "no_brew":
                status = 404
            key = "cask" if spec["category"] == "cask-install" else "formula"
            body = {"category": spec["category"], "start_date": "2026-08-22", "end_date": "2026-09-21",
                    "items": brew_items(key, BREW[(spec["category"], spec["period"])])}
        elif kind == "brew_meta":
            if variant == "no_brew":
                status = 404
            same = variant == "codex_formula_same"
            body = {"name": spec["name"], "desc": "synthetic",
                    "homepage": "https://github.com/openai/codex" if same else "https://example.com/another-codex",
                    "urls": {"stable": {"url": "https://example.com/src.tar.gz"}}}
        if status == 200:
            path = raw / spec["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(body), encoding="utf-8")
        entries.append({**spec, "status": status})
    (raw / "manifest.json").write_text(json.dumps({"fetch_date_utc": fetch_date.isoformat(), "entries": entries}), encoding="utf-8")


FAILS: list[str] = []
N_CHECKS = 0


def check(name: str, got, want, tol: float = 0.0) -> None:
    global N_CHECKS
    N_CHECKS += 1
    ok = abs(got - want) <= tol if (tol and got is not None) else got == want
    if not ok:
        FAILS.append(name)
    print(f"  {'ok ' if ok else 'NG '} {name}: {got!r}" + ("" if ok else f"  (期待 {want!r})"))


def run(variant: str, fetch_date: date) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp), fetch_date, variant)
        return M.analyze(tmp)


def main() -> None:
    D = date(2026, 9, 21)
    print("== 前提（曜日）")
    check("2026-09-19 は土曜", date(2026, 9, 19).weekday(), 5)
    check("2026-03-24 は火曜", date(2026, 3, 24).weekday(), 1)
    check("2026-02-11 は水曜", E.weekday(), 2)
    check("2026-06-07 は日曜", date(2026, 6, 7).weekday(), 6)
    check("2026-07-10 は金曜", date(2026, 7, 10).weekday(), 4)
    check("2026-05-04 は月曜", CODEX_UNPUBLISHED.weekday(), 0)

    print("== 閾値の境界（0001: 0.40 以上 / 0.20 未満、1.5 以上 / 1.2 未満、1.2 以上、20 日未満）")
    check("P1a 0.40", M.verdict_p1a(400 / 1000), "支持")
    check("P1a 0.399", M.verdict_p1a(399 / 1000), "保留")
    check("P1a 0.20", M.verdict_p1a(200 / 1000), "保留")
    check("P1a 0.199", M.verdict_p1a(199 / 1000), "不支持")
    check("P1b 1.5", M.verdict_p1b(1500 / 1000), "支持")
    check("P1b 1.49", M.verdict_p1b(1.49), "保留")
    check("P1b 1.2", M.verdict_p1b(1200 / 1000), "保留")
    check("P1b 1.19", M.verdict_p1b(1.19), "不支持")
    check("P2 1.2・20 日", M.verdict_p2(1200 / 1000, 20, 20), "跳ねる")
    check("P2 1.19", M.verdict_p2(1.19, 50, 50), "跳ねない")
    check("P2 19 日", M.verdict_p2(2.0, 19, 100), "判定不能")
    check("P2 他の群が 19 日", M.verdict_p2(2.0, 100, 19), "判定不能")
    check("B +1.0%", M.check_b(1010, 1000)["ok"], True)
    check("B +1.1%", M.check_b(1011, 1000)["ok"], False)
    check("B −1.1%", M.check_b(989, 1000)["ok"], False)
    check("安定版の判定", [M.is_stable(v) for v in ("1.2.3", "1.2.3-alpha.1", "1.2.3-linux-x64")], [True, False, False])
    check("年で区切る", L.range_chunks(date(2025, 1, 1), date(2026, 9, 20)),
          [(date(2025, 1, 1), date(2025, 12, 31)), (date(2026, 1, 1), date(2026, 9, 20))])

    print("== base（取得日 2026-09-21）")
    r = run("base", D)
    check("最終日", r["last_day"], date(2026, 9, 19))
    check("直近 30 日の窓", r["window_30d"], (date(2026, 8, 21), date(2026, 9, 19)))
    check("A", r["A"]["ok"], True)
    check("A 公開日", {t: r["A"]["per_tool"][t]["pub_date"] for t in L.TOOLS}, PUB)
    # codex の time には取り下げ版が 1 つ多い
    check("A codex 取り下げ版", r["A"]["per_tool"]["codex"]["n_stable_time"] - r["A"]["per_tool"]["codex"]["n_stable_listed"], 1)
    check("B", r["B"]["ok"], True)
    check("B 差", [r["B"]["per_tool"][t]["rel_diff"] for t in L.TOOLS], [0.0, 0.0, 0.0])
    # P1a: プラットフォーム版 200+150+50+20+20+10+10 = 460、全体 1040（musl の 40 は分母だけ）
    check("P1a プラットフォーム版の合計", r["P1a"]["platform_total"], 460)
    check("P1a 全版の合計", r["P1a"]["total"], 1040)
    check("P1a キー数", r["P1a"]["n_platform_keys"], 7)
    check("P1a s", r["P1a"]["s"], 460 / 1040, 1e-12)
    check("P1a 判定", r["P1a"]["verdict"], "支持")
    # P1b: 前後 28 日は平日 20・週末 8 なので中央値は平日の水準。codex 1000→2000、claude 1000→1100、gemini 1000→900
    check("P1b 窓", (r["P1b"]["per_tool"]["codex"]["before"], r["P1b"]["per_tool"]["codex"]["after"]),
          ((date(2026, 1, 14), date(2026, 2, 10)), (date(2026, 2, 25), date(2026, 3, 24))))
    check("P1b codex 中央値", (r["P1b"]["per_tool"]["codex"]["median_before"], r["P1b"]["per_tool"]["codex"]["median_after"]), (1000, 2000))
    check("P1b 比", [r["P1b"]["per_tool"][t]["ratio"] for t in L.TOOLS], [1.1, 2.0, 0.9])
    check("P1b 差の差", r["P1b"]["did"], 2.0, 1e-12)
    check("P1b 判定", r["P1b"]["verdict"], "支持")
    # P2: 窓は火 03-24〜土 09-19（25 週＋火〜土）。火水木金は 26 回、月は 25 回 → 平日 129 日
    #   codex: 火・水 52 ＋ 月 06-08（前日の日曜がリリース）＋ 金 07-10（23:30 UTC）＋ 月 05-04（取り下げ版）= 55、残り 74
    #   gemini: 木・金 52、残り 77。claude: 毎日リリースなので「それ以外」が 0 日
    check("P2 窓", r["P2"]["codex"]["window"], (date(2026, 3, 24), date(2026, 9, 19)))
    check("P2 codex 日数", (r["P2"]["codex"]["n_release"], r["P2"]["codex"]["n_other"]), (55, 74))
    check("P2 codex 中央値", (r["P2"]["codex"]["median_release"], r["P2"]["codex"]["median_other"]), (3000, 2000))
    check("P2 codex", (r["P2"]["codex"]["ratio"], r["P2"]["codex"]["verdict"]), (1.5, "跳ねる"))
    check("P2 gemini 日数", (r["P2"]["gemini"]["n_release"], r["P2"]["gemini"]["n_other"]), (52, 77))
    check("P2 gemini", (r["P2"]["gemini"]["ratio"], r["P2"]["gemini"]["verdict"]), (990 / 900, "跳ねない"))
    check("P2 claude", (r["P2"]["claude"]["n_release"], r["P2"]["claude"]["n_other"], r["P2"]["claude"]["verdict"]), (129, 0, "判定不能"))
    # P3: 30 日の窓は金 08-21〜土 09-19（平日 21・週末 9。火 4・水 4・木 4・金 5）
    #   codex 8×3000 + 13×2000 + 9×600 = 55,400 / claude 21×550 + 9×275 = 14,025 / gemini 9×990 + 12×900 + 9×225 = 21,735
    p30 = r["P3"]["periods"]["30d"]
    check("P3 npm 30 日", p30["npm"], {"claude": 14025, "codex": 55400, "gemini": 21735})
    check("P3 Homebrew 30d", p30["brew"], {"claude": 6000, "codex": 7000, "gemini": 3000})
    check("P3 順位", (p30["npm_rank"], p30["brew_rank"], p30["same_order"]),
          (["codex", "gemini", "claude"], ["codex", "claude", "gemini"], False))
    # 90 日の窓は月 06-22〜土 09-19（木 13・金 13・他の平日 39・週末 25）: 26×990 + 39×900 + 25×225 = 66,465
    check("P3 npm 90 日 gemini", r["P3"]["periods"]["90d"]["npm"]["gemini"], 66465)
    check("P3 365d（一覧に無い cask は 0）", r["P3"]["periods"]["365d"]["brew"], {"claude": 80000, "codex": 70000, "gemini": 30000})
    check("P3 formula codex は別物", r["P3"]["codex_formula"]["same_tool"], False)
    check("参考 install-on-request", r["P3"]["reference_install_on_request"]["30d"], {"gemini-cli": 2900, "codex": 450})
    # 記述
    check("(a) Linux の割合", r["desc"]["a_claude_platform_share"]["linux_share"], 135 / 200, 1e-12)
    check("(a) 8 パッケージの合計", r["desc"]["a_claude_platform_share"]["total"], 200 * 30)
    check("(b) 平日÷週末", [round(r["desc"]["b_weekday_weekend"][t]["ratio"], 6) for t in L.TOOLS], [2.0, round(2000 / 600, 6), 4.0])
    check("(c) claude 04-13 前後", (r["desc"]["c_claude_split"]["claude"]["before"], r["desc"]["c_claude_split"]["claude"]["after"],
                                   r["desc"]["c_claude_split"]["claude"]["ratio"]),
          ((date(2026, 3, 16), date(2026, 4, 12)), (date(2026, 4, 27), date(2026, 5, 24)), 0.5))
    check("(c) 他の 2 つ", (r["desc"]["c_claude_split"]["codex"]["ratio"], r["desc"]["c_claude_split"]["gemini"]["ratio"]), (1.0, 1.0))
    check("(d) gemini 火水÷他", r["desc"]["d_tue_wed"]["gemini"]["ratio"], 900 / 990, 1e-12)
    check("(d) codex 火水÷他", r["desc"]["d_tue_wed"]["codex"]["ratio"], 1.5)
    check("レジストリ: codex の別名の最初", r["registry_checks"]["codex_first_alias_version"][1], E)
    check("レジストリ: claude の別パッケージの最初", r["registry_checks"]["claude_first_platform_dep_version"][1], SPLIT)
    check("版別の合計と point", r["versions_total_vs_point_lastweek"]["codex"]["versions_total"], 1040)
    check("C", (r["C"]["ok"], r["C"]["determinate"]), (True, ["P1a", "P1b", "P2:codex", "P2:gemini"]))
    json.dumps(M.to_jsonable(r), ensure_ascii=False)  # JSON にできること

    print("== 壊した合成データ")
    r = run("missing_day", D)
    check("日付の欠け → A 不通過", (r["A"]["ok"], r["A"]["per_tool"]["codex"]["missing_dates"]), (False, [date(2026, 3, 1)]))
    check("A 不通過なら予測は出さない", "P1a" in r, False)
    r = run("missing_time", D)
    check("公開時刻の無い安定版 → A 不通過", (r["A"]["ok"], r["A"]["per_tool"]["claude"]["stable_missing_time"]), (False, ["99.0.0"]))
    r = run("b_fail", D)
    check("point が 2% ずれ → B 不通過", (r["B"]["ok"], [r["B"]["per_tool"][t]["ok"] for t in L.TOOLS]), (False, [True, True, False]))
    r = run("no_brew", D)
    check("Homebrew なし → P3 だけ落ちる", ("dropped" in r["P3"], r["P1a"]["verdict"], r["C"]["ok"]), (True, "支持", True))
    r = run("no_versions", D)
    check("版別なし → P1a だけ落ちる", (r["P1a"]["verdict"], r["P1b"]["verdict"]), ("判定不能", "支持"))
    r = run("codex_formula_same", D)
    check("formula codex が同じツール → 足す", (r["P3"]["codex_formula"]["same_tool"], r["P3"]["periods"]["30d"]["brew"]["codex"]), (True, 7500))

    print("== 取得日を変える（2026-08-10 → 最終日 08-08、30 日 07-10〜、180 日 02-10〜）")
    r = run("base", date(2026, 8, 10))
    check("窓", (r["last_day"], r["window_30d"], r["P2"]["codex"]["window"]),
          (date(2026, 8, 8), (date(2026, 7, 10), date(2026, 8, 8)), (date(2026, 2, 10), date(2026, 8, 8))))
    check("A・B", (r["A"]["ok"], r["B"]["ok"]), (True, True))
    check("P1b は取得日によらない", r["P1b"]["did"], 2.0, 1e-12)

    print(f"\n{N_CHECKS - len(FAILS)}/{N_CHECKS} 通過" + ("" if not FAILS else f"、NG: {FAILS}"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()

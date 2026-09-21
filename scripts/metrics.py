"""decisions/0001 で凍結した定義どおりの集計。標準ライブラリのみ。

analyze(raw_dir) が生データのフォルダ（fetch.py の出力、または test_synthetic.py の合成データ）を読み、
撤退基準 A・B、予測 P1a・P1b・P2・P3、記述 (a)〜(d) をまとめた dict を返す。表示とファイル出力は analyze.py。

0001 に書かれていない細部の決め（値を取得する前に、このファイルのコミットで固定する）:
- 「直近 30 日・90 日・180 日・365 日」は、集計に使う最終日（取得日の 2 日前）を含む n 日間
- 撤退基準 B の「明示した 30 日間」は、上の直近 30 日
- 版の一覧はレジストリの `time` のキー（created・modified を除く）。公開後に取り下げられた版も「公開された版」に含める。
  撤退基準 A の「全安定版の公開時刻が取れる」は、`versions` にある安定版がすべて `time` にあること
- パッケージの公開日は、`time` にある版の公開時刻の最小（UTC の日付）
- P2 の「前日」は暦の前日（月曜の前日は日曜）
- 記述 (b) と (d) の比は、P1b・P2 と同じく中央値どうしの比
- 記述 (a) の Linux は、パッケージ名に `linux` を含むもの（musl 版を含む）
- formula `codex` を同じツールとみなす条件は、Homebrew のメタデータの homepage か urls.stable.url か urls.head.url に
  `github.com/openai/codex` を含むこと
- 撤退基準 C の P2 は、3 ツールのどれか 1 つで「跳ねる」か「跳ねない」が出れば「出た」と数える

取得後に足した決め（2026-09-21。JSON の構造だけを見て、install 数の値を表示する前に決めた）:
- Homebrew の analytics は、名前ごとにオプション違い（`gemini-cli --HEAD` など）の行を持つ。同じ名前の行は合算する
"""
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rawlayout as L  # noqa: E402

TOOLS = L.TOOLS
PLATFORM_SUFFIXES = ("-darwin-arm64", "-darwin-x64", "-linux-arm64", "-linux-x64", "-win32-arm64", "-win32-x64")
E_CODEX = date(2026, 2, 11)
P1B_BEFORE = (date(2026, 1, 14), date(2026, 2, 10))
P1B_AFTER = (date(2026, 2, 25), date(2026, 3, 24))
E_CLAUDE_SPLIT = date(2026, 4, 13)

P1A_SUPPORT, P1A_REJECT = 0.40, 0.20
P1B_SUPPORT, P1B_REJECT = 1.5, 1.2
P2_JUMP, P2_MIN_DAYS, P2_DAYS = 1.2, 20, 180
B_TOLERANCE = 0.01

BREW_SOURCES = {  # P3（0001）。formula codex は同じツールと確認できた場合だけ足す
    "claude": [("cask", "claude-code"), ("cask", "claude-code@latest")],
    "codex": [("cask", "codex")],
    "gemini": [("formula", "gemini-cli")],
}
BREW_CATEGORY = {"formula": "install", "cask": "cask-install"}
NPM_DAYS = {"30d": 30, "90d": 90, "365d": 365}


# ---------- 小道具

def days(w: tuple[date, date]) -> list[date]:
    s, e = w
    return [s + timedelta(days=i) for i in range((e - s).days + 1)]


def step_windows(e: date) -> tuple[tuple[date, date], tuple[date, date]]:
    """前 28 日（e−28〜e−1）と、移行の 14 日を空けた後 28 日（e+14〜e+41）。"""
    return (e - timedelta(days=28), e - timedelta(days=1)), (e + timedelta(days=14), e + timedelta(days=41))


assert step_windows(E_CODEX) == (P1B_BEFORE, P1B_AFTER), "P1b の窓が 0001 の日付と一致しない"


def is_stable(version: str) -> bool:
    return "-" not in version


def is_platform_version(version: str) -> bool:
    return version.endswith(PLATFORM_SUFFIXES)


def parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def ratio(a, b):
    return a / b if (a is not None and b) else None


def verdict_p1a(s):
    if s is None:
        return "判定不能"
    return "支持" if s >= P1A_SUPPORT else "不支持" if s < P1A_REJECT else "保留"


def verdict_p1b(x):
    if x is None:
        return "判定不能"
    return "支持" if x >= P1B_SUPPORT else "不支持" if x < P1B_REJECT else "保留"


def verdict_p2(x, n_r: int, n_n: int):
    if n_r < P2_MIN_DAYS or n_n < P2_MIN_DAYS or x is None:
        return "判定不能"
    return "跳ねる" if x >= P2_JUMP else "跳ねない"


# ---------- 読み込み

class Raw:
    def __init__(self, raw_dir):
        self.dir = Path(raw_dir)
        self.manifest = json.loads((self.dir / "manifest.json").read_text(encoding="utf-8"))
        self.fetch_date = date.fromisoformat(self.manifest["fetch_date_utc"])

    def entries(self, kind: str, **match) -> list[dict]:
        return [e for e in self.manifest["entries"]
                if e["kind"] == kind and e["status"] == 200 and all(e.get(k) == v for k, v in match.items())]

    def load(self, entry: dict):
        return json.loads((self.dir / entry["file"]).read_text(encoding="utf-8"))

    def load_one(self, kind: str, **match):
        found = self.entries(kind, **match)
        return self.load(found[0]) if found else None


def load_daily(raw: Raw, kind: str, package: str) -> dict[date, int]:
    daily: dict[date, int] = {}
    for e in raw.entries(kind, package=package):
        body = raw.load(e)
        if body.get("package") != package:
            raise ValueError(f"package が一致しない: {e['file']}")
        for row in body["downloads"]:
            d, v = date.fromisoformat(row["day"]), int(row["downloads"])
            if d in daily and daily[d] != v:
                raise ValueError(f"同じ日の値が食い違う: {package} {d}")
            daily[d] = v
    return daily


def registry_summary(reg: dict) -> dict:
    times = {v: parse_time(t) for v, t in reg["time"].items() if v not in ("created", "modified")}
    in_versions = set(reg.get("versions", {}))
    stable = [v for v in times if is_stable(v)]
    return {
        "n_versions_time": len(times),
        "n_versions_listed": len(in_versions),
        "n_stable_time": len(stable),
        "n_stable_listed": sum(1 for v in in_versions if is_stable(v)),
        "stable_missing_time": sorted(v for v in in_versions if is_stable(v) and v not in times),
        "pub_date": min(times.values()).date(),
        "last_stable_date": max(times[v] for v in stable).date() if stable else None,
        "release_days": Counter(times[v].date() for v in stable),
        "times": times,
    }


def first_version_with_dep(reg: dict, times: dict, pred) -> tuple[str, date] | None:
    """optionalDependencies が条件を満たす最初の安定版（公開時刻の順）。"""
    hits = []
    for v, meta in reg.get("versions", {}).items():
        if is_stable(v) and v in times and any(pred(k, str(spec)) for k, spec in (meta.get("optionalDependencies") or {}).items()):
            hits.append((times[v], v))
    if not hits:
        return None
    t, v = min(hits)
    return v, t.date()


# ---------- 撤退基準

def check_a_daily(daily: dict[date, int], pub_date: date, last: date) -> dict:
    expected = days((pub_date, last))
    missing = [d for d in expected if d not in daily]
    nonzero = [d for d in expected if daily.get(d, 0) > 0]
    first_nonzero = min(nonzero) if nonzero else None
    zero_after = [d for d in expected if first_nonzero and d > first_nonzero and daily.get(d) == 0]
    return {
        "pub_date": pub_date, "last_day": last, "n_expected": len(expected), "n_missing": len(missing),
        "missing_dates": missing[:20], "first_nonzero": first_nonzero,
        "n_zero_days_after_first_nonzero": len(zero_after), "zero_days": zero_after[:20],
        "ok": not missing,
    }


def check_b(range_sum: int, point: int | None) -> dict:
    rel = (range_sum - point) / point if point else None
    return {"range_sum": range_sum, "point": point, "rel_diff": rel, "ok": rel is not None and abs(rel) <= B_TOLERANCE}


# ---------- 予測

def p1a(version_downloads: dict[str, int]) -> dict:
    total = sum(version_downloads.values())
    plat = {k: v for k, v in version_downloads.items() if is_platform_version(k)}
    by_suffix = {s: sum(v for k, v in plat.items() if k.endswith(s)) for s in PLATFORM_SUFFIXES}
    stable = sum(v for k, v in version_downloads.items() if is_stable(k))
    s = ratio(sum(plat.values()), total)
    return {
        "n_keys": len(version_downloads), "n_platform_keys": len(plat),
        "total": total, "platform_total": sum(plat.values()), "stable_total": stable,
        "other_prerelease_total": total - sum(plat.values()) - stable,
        "by_suffix": by_suffix, "s": s, "verdict": verdict_p1a(s),
    }


def step_ratio(daily: dict[date, int], e: date) -> dict:
    before, after = step_windows(e)
    try:
        mb, ma = median(daily[d] for d in days(before)), median(daily[d] for d in days(after))
    except KeyError:
        mb = ma = None
    return {"before": before, "after": after, "median_before": mb, "median_after": ma, "ratio": ratio(ma, mb)}


def p1b(dailies: dict[str, dict[date, int]]) -> dict:
    per = {t: step_ratio(dailies[t], E_CODEX) for t in TOOLS}
    others = [per[t]["ratio"] for t in TOOLS if t != "codex"]
    others_mean = sum(others) / len(others) if all(x is not None for x in others) else None
    did = ratio(per["codex"]["ratio"], others_mean)
    return {"per_tool": per, "others_mean": others_mean, "did": did, "verdict": verdict_p1b(did)}


def p2(daily: dict[date, int], release_days, last: date) -> dict:
    w = L.window(last, P2_DAYS)
    r, n = [], []
    for d in days(w):
        if d.weekday() >= 5:
            continue
        (r if (d in release_days or d - timedelta(days=1) in release_days) else n).append(daily[d])
    mr, mn = (median(r) if r else None), (median(n) if n else None)
    x = ratio(mr, mn)
    return {
        "window": w, "n_release_days_in_window": sum(1 for d in days(w) if d in release_days),
        "n_release": len(r), "n_other": len(n), "median_release": mr, "median_other": mn,
        "ratio": x, "verdict": verdict_p2(x, len(r), len(n)),
    }


def brew_count(body: dict | None, name: str) -> int | None:
    """analytics の JSON は {"formulae": {名前: [{"formula" か "cask": "名前 [オプション]", "count": "1,234"}, …]}}。
    同じ名前のオプション違い（`--HEAD` など）は合算する。一覧に無ければ None。"""
    if body is None or name not in body["formulae"]:
        return None
    return sum(int(str(row["count"]).replace(",", "")) for row in body["formulae"][name])


def formula_is_openai_codex(meta: dict | None) -> dict:
    if meta is None:
        return {"same_tool": False, "reason": "formula codex のメタデータが取れない", "homepage": None, "desc": None, "stable_url": None}
    urls = meta.get("urls") or {}
    fields = [meta.get("homepage"), (urls.get("stable") or {}).get("url"), (urls.get("head") or {}).get("url")]
    hit = any("github.com/openai/codex" in (f or "").lower() for f in fields)
    return {"same_tool": hit, "reason": "homepage・urls に github.com/openai/codex を" + ("含む" if hit else "含まない"),
            "homepage": meta.get("homepage"), "desc": meta.get("desc"), "stable_url": fields[1]}


def rank(values: dict[str, int | None]) -> list[str] | None:
    if any(v is None for v in values.values()):
        return None
    return sorted(values, key=lambda t: -values[t])


def p3(raw: Raw, dailies: dict[str, dict[date, int]], last: date) -> dict:
    codex_formula = formula_is_openai_codex(raw.load_one("brew_meta", type="formula", name="codex"))
    sources = {t: list(v) for t, v in BREW_SOURCES.items()}
    if codex_formula["same_tool"]:
        sources["codex"].append(("formula", "codex"))
    out = {"codex_formula": codex_formula, "sources": sources, "periods": {}}
    for period, n in NPM_DAYS.items():
        w = L.window(last, n)
        npm = {t: sum(dailies[t].get(d, 0) for d in days(w)) for t in TOOLS}
        bodies = {typ: raw.load_one("brew_analytics", category=cat, period=period) for typ, cat in BREW_CATEGORY.items()}
        parts = {t: {f"{typ}:{name}": brew_count(bodies[typ], name) for typ, name in sources[t]} for t in TOOLS}
        # 一覧に無い（＝期間内の install が記録されていない）ものは 0 として足す。analytics 自体が取れなければ None
        brew = {t: (None if any(bodies[typ] is None for typ, _ in sources[t]) else sum(v or 0 for v in parts[t].values()))
                for t in TOOLS}
        any_body = next((b for b in bodies.values() if b), None)
        nr, br = rank(npm), rank(brew)
        out["periods"][period] = {
            "npm_window": w, "npm": npm, "npm_rank": nr,
            "brew_window": (any_body.get("start_date"), any_body.get("end_date")) if any_body else None,
            "brew_parts": parts, "brew": brew, "brew_rank": br,
            "same_order": (nr == br) if (nr and br) else None,
        }
    # 参考（判定に使わない）: formula の install-on-request
    out["reference_install_on_request"] = {
        period: {name: brew_count(raw.load_one("brew_analytics", category="install-on-request", period=period), name)
                 for name in ("gemini-cli", "codex")}
        for period in NPM_DAYS
    }
    return out


# ---------- 記述

def desc_platform_share(raw: Raw, last: date) -> dict:
    w = L.window(last, 30)
    totals = {}
    for e in raw.entries("npm_range_platform"):
        daily = load_daily(raw, "npm_range_platform", e["package"])
        totals[e["package"]] = sum(daily.get(d, 0) for d in days(w))
    total = sum(totals.values())
    linux = sum(v for k, v in totals.items() if "linux" in k)
    return {"window": w, "totals": totals, "total": total, "linux_share": ratio(linux, total),
            "shares": {k: ratio(v, total) for k, v in totals.items()}}


def desc_weekday_weekend(daily: dict[date, int], last: date) -> dict:
    w = L.window(last, P2_DAYS)
    wd = [daily[d] for d in days(w) if d.weekday() < 5]
    we = [daily[d] for d in days(w) if d.weekday() >= 5]
    return {"window": w, "median_weekday": median(wd), "median_weekend": median(we), "ratio": ratio(median(wd), median(we))}


def desc_tue_wed(daily: dict[date, int], last: date) -> dict:
    w = L.window(last, P2_DAYS)
    tw = [daily[d] for d in days(w) if d.weekday() in (1, 2)]
    ot = [daily[d] for d in days(w) if d.weekday() in (0, 3, 4)]
    return {"window": w, "n_tue_wed": len(tw), "n_other": len(ot), "median_tue_wed": median(tw), "median_other": median(ot),
            "ratio": ratio(median(tw), median(ot))}


# ---------- まとめ

def analyze(raw_dir) -> dict:
    raw = Raw(raw_dir)
    last = L.last_day(raw.fetch_date)
    w30 = L.window(last, 30)
    out: dict = {"fetch_date_utc": raw.fetch_date, "last_day": last, "window_30d": w30,
                 "n_requests": len(raw.manifest["entries"]),
                 "non_200": [{"url": e["url"], "status": e["status"]} for e in raw.manifest["entries"] if e["status"] != 200]}

    regs, dailies = {}, {}
    for t, pkg in L.PACKAGES.items():
        reg = raw.load_one("registry", package=pkg)
        regs[t] = (reg, registry_summary(reg)) if reg else (None, None)
        dailies[t] = load_daily(raw, "npm_range", pkg)

    # A
    a = {}
    for t in TOOLS:
        reg, rs = regs[t]
        if rs is None:
            a[t] = {"ok": False, "reason": "レジストリが取れない"}
            continue
        a[t] = check_a_daily(dailies[t], rs["pub_date"], last)
        a[t].update({k: rs[k] for k in ("n_versions_time", "n_versions_listed", "n_stable_time", "n_stable_listed",
                                          "stable_missing_time", "last_stable_date")})
        a[t]["ok"] = a[t]["ok"] and not rs["stable_missing_time"] and rs["n_stable_time"] > 0
    out["A"] = {"per_tool": a, "ok": all(x["ok"] for x in a.values())}

    # B
    b = {}
    for t, pkg in L.PACKAGES.items():
        point = raw.load_one("npm_point", package=pkg)
        if point and (point.get("start"), point.get("end")) != (w30[0].isoformat(), w30[1].isoformat()):
            raise ValueError(f"point の期間が要求と違う: {pkg} {point.get('start')}〜{point.get('end')}")
        b[t] = check_b(sum(dailies[t].get(d, 0) for d in days(w30)), point["downloads"] if point else None)
    out["B"] = {"window": w30, "per_tool": b, "ok": all(x["ok"] for x in b.values())}
    if not out["A"]["ok"]:
        return out

    # P1a（版別が取れなければ落とす）
    versions = raw.load_one("npm_versions", package=L.PACKAGES["codex"])
    out["P1a"] = p1a(versions["downloads"]) if versions else {"verdict": "判定不能", "s": None, "reason": "版別が取れない"}
    out["P1a_reference_other_tools"] = {}
    for t in ("claude", "gemini"):
        v = raw.load_one("npm_versions", package=L.PACKAGES[t])
        if v:
            r = p1a(v["downloads"])
            out["P1a_reference_other_tools"][t] = {k: r[k] for k in ("n_keys", "n_platform_keys", "total", "platform_total", "s")}
    out["versions_total_vs_point_lastweek"] = {}
    for t, pkg in L.PACKAGES.items():
        v, pt = raw.load_one("npm_versions", package=pkg), raw.load_one("npm_point_lastweek", package=pkg)
        if v and pt:
            out["versions_total_vs_point_lastweek"][t] = {
                "versions_total": sum(v["downloads"].values()), "point_lastweek": pt["downloads"],
                "point_window": (pt.get("start"), pt.get("end"))}

    out["P1b"] = p1b(dailies)
    out["P2"] = {t: p2(dailies[t], regs[t][1]["release_days"], last) for t in TOOLS}
    has_brew = bool(raw.entries("brew_analytics"))
    out["P3"] = p3(raw, dailies, last) if has_brew else {"dropped": "Homebrew が取れない"}

    # 凍結した日付とレジストリの突き合わせ（報告だけ）
    out["registry_checks"] = {
        "codex_first_alias_version": first_version_with_dep(
            regs["codex"][0], regs["codex"][1]["times"], lambda k, spec: spec.startswith("npm:@openai/codex@")),
        "claude_first_platform_dep_version": first_version_with_dep(
            regs["claude"][0], regs["claude"][1]["times"], lambda k, spec: k.startswith(L.CLAUDE_PLATFORM_PREFIX)),
    }

    out["desc"] = {
        "a_claude_platform_share": desc_platform_share(raw, last),
        "b_weekday_weekend": {t: desc_weekday_weekend(dailies[t], last) for t in TOOLS},
        "c_claude_split": {t: step_ratio(dailies[t], E_CLAUDE_SPLIT) for t in TOOLS},
        "d_tue_wed": {t: desc_tue_wed(dailies[t], last) for t in TOOLS},
    }

    determinate = [k for k in ("P1a", "P1b") if out[k]["verdict"] in ("支持", "不支持")]
    determinate += [f"P2:{t}" for t in TOOLS if out["P2"][t]["verdict"] in ("跳ねる", "跳ねない")]
    out["C"] = {"determinate": determinate, "ok": bool(determinate)}
    out["_dailies"] = dailies
    out["_release_days"] = {t: regs[t][1]["release_days"] for t in TOOLS}
    return out


def to_jsonable(x):
    if isinstance(x, dict):
        return {str(k): to_jsonable(v) for k, v in x.items() if not str(k).startswith("_")}
    if isinstance(x, (list, tuple)):
        return [to_jsonable(v) for v in x]
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    return x

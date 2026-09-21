"""decisions/0003 で凍結した定義どおりの集計（Q1・Q2 の判定、Q3・Q4 と突出の追加確認の記述）。標準ライブラリのみ。

0003 に無い実装上の細部（issue・Releases・Hacker News の値を取得する前に、このコミットで固定する）:
- issue の作成日は createdAt の UTC の日付。「初めて issue を立てた人」の最初の issue は、Bot を除いた全 issue のうち作成日時が最小のもの
- 期間 P は [開始日 00:00 UTC, 終了日の翌日 00:00 UTC)。Releases の区間の端は published_at の時刻（秒まで）
- published_at の無いリリースは除く。長さ 0 の区間（同時刻に 2 つの安定版）は按分に入れない。期間と重なる区間が 1 つも無ければ「値なし」
- Hacker News は created_at_i（UTC の秒）で期間に入れ、同じ objectID は 1 回だけ数える
- 比の分母が 0、または分子・分母のどちらかが「値なし」のとき、その指標は「値なし」として n から除く
- Q3 で突出の日を置き換える値は、docs/data/posthoc.json の spikes の baseline（前後 14 日の中央値）
- Q3 の変更履歴の項目は日付（UTC とみなす）だけで当てる
- Q3 の段差の検出で r が同値の最大が続くときは、最も早い日を取る。合成データでは、実際の段差（02-11）より 4 日早い日（02-07）が
  検出日になった（前後 14 日の中央値を使うため、検出日は実際の段差の前後にずれうる）。0003 の窓 [d−7, d] の項目はそのまま出し、
  (d, d+7] の項目と、±7 日の安定版のリリースを「検出日のずれのための参考」として別に出す（Q3 は記述で、判定は無い）
- Q4 の語は大文字小文字を区別しない。ASCII の短い語は英数字の境界つきで当てる（`vs`・`plus`・`pro`・`o3`・`o4` は前後、`gpt` は先頭）。
  vscode・prompt・ChatGPT を拾わないため。同点のいいね数は path の昇順
"""
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from statistics import median

REPOS = {"codex": "openai/codex", "claude": "anthropics/claude-code", "gemini": "google-gemini/gemini-cli"}
TOOLS = tuple(REPOS)
HN_QUERY = {"codex": "codex", "claude": "claude code", "gemini": "gemini cli"}
HN_RE = {t: re.compile(p, re.I) for t, p in {"codex": r"\bcodex\b", "claude": r"\bclaude code\b", "gemini": r"\bgemini cli\b"}.items()}

D1 = timedelta(days=1)
W = (date(2026, 4, 30), date(2026, 5, 6))
BASE_WEEKS = [(date(2026, 4, 2) + timedelta(days=7 * k), date(2026, 4, 8) + timedelta(days=7 * k)) for k in range(4)]
assert BASE_WEEKS[-1][1] + D1 == W[0]
JAN, AUG = (date(2026, 1, 1), date(2026, 1, 31)), (date(2026, 8, 1), date(2026, 8, 31))

Q1_RATIO = 1.5
NPM_WEEK_RATIO = 49.2           # 既知（0003）
NPM_MONTH_RATIO_ADJ = 17.64     # 既知（0003）: 36.35 ÷ 2.06
Q2_SUPPORT, Q2_REJECT = 5.88, 11.76
Q3_START, Q3_MIN_R, Q3_MIN_VALID, Q3_MIN_GAP = date(2025, 10, 1), 1.5, 10, 28

ZENN_CATEGORIES = [
    ("乗り換え・比較", r"claude|cursor|gemini|copilot|比較|乗り換え|移行|(?<![a-z0-9])vs(?![a-z0-9])"),
    ("料金・制限", r"料金|プラン|制限|レート|リミット|課金|無料|コスト|クレジット|(?<![a-z0-9])plus(?![a-z0-9])|(?<![a-z0-9])pro(?![a-z0-9])"),
    ("新モデル", r"(?<![a-z0-9])gpt|モデル|(?<![a-z0-9])o3(?![a-z0-9])|(?<![a-z0-9])o4(?![a-z0-9])"),
    ("使い方・設定", r"入門|使い方|設定|agents|mcp|tips|導入|インストール|始め|ガイド|まとめ|チート"),
]
ZENN_RE = [(name, re.compile(p, re.I)) for name, p in ZENN_CATEGORIES]
SPIKE_NOTE_RE = re.compile(r"update|npm|install|download|retry|loop", re.I)
SPIKE_ISSUE_RE = re.compile(r"npm|install|update|download", re.I)


# ---------- 小道具

def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def bounds(p: tuple[date, date]) -> tuple[datetime, datetime]:
    return (datetime(p[0].year, p[0].month, p[0].day, tzinfo=timezone.utc),
            datetime(p[1].year, p[1].month, p[1].day, tzinfo=timezone.utc) + D1)


def n_days(p: tuple[date, date]) -> int:
    return (p[1] - p[0]).days + 1


def ratio(a, b):
    return a / b if (a is not None and b is not None and b != 0) else None


# ---------- issue

def human_issues(issues: list[dict]) -> list[dict]:
    return [i for i in issues if not (i.get("author") and i["author"].get("__typename") == "Bot")]


def issue_count(issues: list[dict], p) -> int:
    s, e = bounds(p)
    return sum(1 for i in human_issues(issues) if s <= parse_ts(i["createdAt"]) < e)


def authors(issues: list[dict], p) -> int:
    s, e = bounds(p)
    return len({i["author"]["login"] for i in human_issues(issues) if i.get("author") and s <= parse_ts(i["createdAt"]) < e})


def first_time_authors(issues: list[dict], p) -> int:
    first: dict[str, datetime] = {}
    for i in human_issues(issues):
        if i.get("author"):
            t = parse_ts(i["createdAt"])
            login = i["author"]["login"]
            if login not in first or t < first[login]:
                first[login] = t
    s, e = bounds(p)
    return sum(1 for t in first.values() if s <= t < e)


# ---------- GitHub Releases

def stable_intervals(releases: list[dict], fetch_time: datetime) -> list[tuple[datetime, datetime, int, str]]:
    st = sorted(((parse_ts(r["published_at"]), sum(a["download_count"] for a in r.get("assets", [])), r["tag_name"])
                 for r in releases if not r.get("prerelease") and not r.get("draft") and r.get("published_at")))
    out = []
    for k, (t, d, tag) in enumerate(st):
        end = st[k + 1][0] if k + 1 < len(st) else fetch_time
        out.append((t, end, d, tag))
    return out


def release_rate(intervals, p) -> float | None:
    s, e = bounds(p)
    total, hit = 0.0, False
    for a, b, d, _ in intervals:
        length = (b - a).total_seconds()
        overlap = (min(b, e) - max(a, s)).total_seconds()
        if length > 0 and overlap > 0:
            total += d * overlap / length
            hit = True
    return total / n_days(p) if hit else None


# ---------- Hacker News

def hn_count(hits: list[dict], tool: str, p) -> int:
    s, e = bounds(p)
    seen = set()
    for h in hits:
        if h["objectID"] not in seen and s.timestamp() <= h["created_at_i"] < e.timestamp() and HN_RE[tool].search(h.get("title") or ""):
            seen.add(h["objectID"])
    return len(seen)


# ---------- Q1・Q2

def week_ratio(fn) -> dict:
    spike = fn(W)
    base = [fn(b) for b in BASE_WEEKS]
    mean = sum(base) / len(base) if all(x is not None for x in base) else None
    return {"spike_week": spike, "base_weeks": base, "base_mean": mean, "ratio": ratio(spike, mean)}


def month_ratio(fn) -> dict:
    jan, aug = fn(JAN), fn(AUG)
    return {"jan": jan, "aug": aug, "ratio": ratio(aug, jan)}


def verdict_q1(ratios: dict[str, float | None]) -> dict:
    avail = {k: v for k, v in ratios.items() if v is not None}
    n, k = len(avail), sum(1 for v in avail.values() if v >= Q1_RATIO)
    if n < 2:
        v = "判定不能"
    elif k >= math.ceil(0.75 * n):
        v = "人の流入と整合（予測は不支持）"
    elif k <= math.floor(0.25 * n):
        v = "人の流入とは整合しない（予測を支持）"
    else:
        v = "保留"
    return {"n": n, "k": k, "verdict": v}


def verdict_q2(ratios: dict[str, float | None]) -> dict:
    avail = [v for v in ratios.values() if v is not None]
    if len(avail) < 2:
        return {"n": len(avail), "G": None, "verdict": "判定不能"}
    g = median(avail)
    return {"n": len(avail), "G": g, "verdict": "支持" if g <= Q2_SUPPORT else "不支持" if g >= Q2_REJECT else "保留"}


def indicators(issues, intervals, hits, tool: str, kind: str) -> dict:
    """kind = 'week'（Q1。作成者は「初めて」）か 'month'（Q2。作成者は期間内の人数）。"""
    f = week_ratio if kind == "week" else month_ratio
    return {
        "a_issues": f(lambda p: issue_count(issues, p)) if issues is not None else None,
        "b_authors": f(lambda p: (first_time_authors if kind == "week" else authors)(issues, p)) if issues is not None else None,
        "c_releases": f(lambda p: release_rate(intervals, p)) if intervals is not None else None,
        "d_hn": f(lambda p: hn_count(hits, tool, p)) if hits is not None else None,
    }


def ratios_of(ind: dict) -> dict:
    return {k: (v["ratio"] if v else None) for k, v in ind.items()}


# ---------- Q3

def detect_steps(daily: dict[date, float], start: date, end: date, replace: dict[date, float] | None = None) -> list[dict]:
    val = {d: (replace or {}).get(d, v) for d, v in daily.items()}
    r: dict[date, float] = {}
    d = start
    while d + timedelta(days=13) <= end:
        after = [val[x] for x in (d + timedelta(days=k) for k in range(14)) if val.get(x, 0) > 0]
        before = [val[x] for x in (d - timedelta(days=k) for k in range(1, 15)) if val.get(x, 0) > 0]
        if len(after) >= Q3_MIN_VALID and len(before) >= Q3_MIN_VALID:
            r[d] = median(after) / median(before)
        d += D1
    cands = [d for d, x in r.items() if x >= Q3_MIN_R and x == max(r.get(d + timedelta(days=k), 0) for k in range(-14, 15))]
    kept: list[date] = []
    for d in sorted(cands, key=lambda x: (-r[x], x)):
        if all(abs((d - k).days) >= Q3_MIN_GAP for k in kept):
            kept.append(d)
    return [{"day": d, "r": r[d]} for d in sorted(kept)]


def events_before(day: date, events: list[dict]) -> list[dict]:
    return [e for e in events if day - timedelta(days=7) <= e["date"] <= day]


def chance_rate(events: list[dict], start: date, end: date) -> float:
    days = [start + timedelta(days=k) for k in range((end - start).days + 1)]
    return sum(1 for d in days if events_before(d, events)) / len(days)


# ---------- Q4

def classify_title(title: str) -> str:
    for name, rx in ZENN_RE:
        if rx.search(title or ""):
            return name
    return "その他"


def zenn_monthly(records: list[dict], months: list[str]) -> dict:
    uniq = {}
    for r in records:
        uniq.setdefault(r["path"], r)
    out = {}
    for m in months:
        rows = [r for r in uniq.values() if (r.get("published_at") or "")[:7] == m]
        top = sorted(rows, key=lambda r: (-r.get("liked_count", 0), r["path"]))[:10]
        cats: dict[str, int] = {}
        for r in top:
            c = classify_title(r.get("title", ""))
            cats[c] = cats.get(c, 0) + 1
        out[m] = {
            "n_articles": len(rows),
            "share_title_claude": (sum(1 for r in rows if re.search("claude", r.get("title") or "", re.I)) / len(rows)) if rows else None,
            "top10_categories": cats,
            "top10": [{"title": r.get("title"), "liked_count": r.get("liked_count", 0), "category": classify_title(r.get("title", ""))} for r in top],
        }
    return out


def to_jsonable(x):
    if isinstance(x, dict):
        return {str(k): to_jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_jsonable(v) for v in x]
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    return x


def load_jsonl(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

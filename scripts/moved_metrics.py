"""decisions/0005 で凍結した定義どおりの集計（R1a・R1m・R1b・R3c・R3x の判定、R2・R4・対照・比較表の記述）。標準ライブラリのみ。

0005 に無い実装上の細部（集計を実行する前に、このコミットで固定する）:
- 期間は [開始日 00:00 UTC, 終了日の翌日 00:00 UTC)。「P1 と P2 を合わせた期間」は 2 つの期間の和（04-21・04-22 は入らない）
- 題名が無い issue は、どの規則にも合わないものとして分母に入れる
- R2 の内訳は重なりを除くため、`[MODEL]` 接頭辞 → 「品質」語 → 「利用枠・料金」語 → それ以外、の順で最初に合った区分に入れる
  （判定に使う R1a・R1m・R1b の割合は、重なりを除かずにそれぞれ数える）
- 週あたりの件数 = 件数 ÷ 期間の日数 × 7
- 比較表の「7 日以内に閉じた」は closedAt − createdAt ≤ 7 × 86,400 秒。割合の分母は期間内の Bot 以外の issue 全件
- Hacker News の上位は、0003 の題名の正規表現に合う投稿をポイントの大きい順（同点は古い順）
"""
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proxy_metrics as PM  # noqa: E402

P0 = (date(2026, 1, 7), date(2026, 3, 3))
P1 = (date(2026, 3, 4), date(2026, 4, 20))
P2 = (date(2026, 4, 23), date(2026, 5, 27))
PERIODS = {"P0": P0, "P1": P1, "P2": P2}
assert (PM.n_days(P0), PM.n_days(P1), PM.n_days(P2)) == (56, 48, 35)
HANDLING = (date(2026, 6, 1), date(2026, 8, 31))

SUPPORT, REJECT, MIN_P0 = 1.5, 1.2, 20

RX = {
    "quality": re.compile(r"quality|degrad|worse|dumb|lazy|nerf|hallucinat|forget|lobotom|stupid|less capable|intelligence"
                          r"|ignor\w* (instruction|claude\.md|rule)|not follow|doesn.?t follow", re.I),
    "limits": re.compile(r"rate.?limit|usage limit|limit reached|hit\w* (the |my )?limit|quota|weekly limit|5.?hour|session limit|credit|billing"
                         r"|pricing|\bprice|subscription|overage|max plan|pro plan|plus plan|expensive|token usage|usage (spike|drain|burn)", re.I),
    "other_from_claude": re.compile(r"codex|openai|chatgpt|gpt-?\d", re.I),
    "other_from_codex": re.compile(r"claude|anthropic|\bopus\b|\bsonnet\b", re.I),
    "gpt55": re.compile(r"5\.5"),
}


def title(i: dict) -> str:
    return i.get("title") or ""


def is_model(i: dict) -> bool:
    return title(i).lstrip().upper().startswith("[MODEL]")


def matcher(key: str):
    return is_model if key == "model" else (lambda i: bool(RX[key].search(title(i))))


def in_any(i: dict, periods) -> bool:
    t = PM.parse_ts(i["createdAt"])
    return any(s <= t < e for s, e in (PM.bounds(p) for p in periods))


def share(issues: list[dict], periods, pred) -> dict:
    rows = [i for i in PM.human_issues(issues) if in_any(i, periods)]
    n = sum(1 for i in rows if pred(i))
    return {"n_match": n, "n_total": len(rows), "share": n / len(rows) if rows else None}


def verdict(ratio, n_match_den: int) -> str:
    if ratio is None or n_match_den < MIN_P0:
        return "判定不能"
    return "支持" if ratio >= SUPPORT else "不支持" if ratio < REJECT else "保留"


def share_ratio(issues: list[dict], key: str, num_periods, den_periods=(P0,)) -> dict:
    num, den = share(issues, num_periods, matcher(key)), share(issues, den_periods, matcher(key))
    r = PM.ratio(num["share"], den["share"])
    return {"numerator": num, "denominator": den, "ratio": r, "verdict": verdict(r, den["n_match"])}


def breakdown(issues: list[dict], p, with_model: bool) -> dict:
    """重なりを除いた内訳の、週あたりの件数。"""
    order = (["model"] if with_model else []) + ["quality", "limits"]
    counts = {k: 0 for k in order + ["other"]}
    for i in PM.human_issues(issues):
        if in_any(i, (p,)):
            counts[next((k for k in order if matcher(k)(i)), "other")] += 1
    total = sum(counts.values())
    per_week = {k: v / PM.n_days(p) * 7 for k, v in counts.items()}
    return {"counts": counts, "total": total, "per_week": per_week, "total_per_week": total / PM.n_days(p) * 7}


def weekly_counts(issues: list[dict], start: date, end: date, keys: list[str], with_model: bool) -> list[dict]:
    rows, s = [], start
    human = PM.human_issues(issues)
    while s + timedelta(days=6) <= end:
        p = (s, s + timedelta(days=6))
        inside = [i for i in human if in_any(i, (p,))]
        row = {"week_start": s, "total": len(inside)}
        for k in keys:
            if k != "model" or with_model:
                row[k] = sum(1 for i in inside if matcher(k)(i))
        rows.append(row)
        s += timedelta(days=7)
    return rows


def hn_top(hits: list[dict], tool: str, p, n: int = 5) -> list[dict]:
    s, e = PM.bounds(p)
    seen, rows = set(), []
    for h in hits:
        if h["objectID"] not in seen and s.timestamp() <= h["created_at_i"] < e.timestamp() and PM.HN_RE[tool].search(h.get("title") or ""):
            seen.add(h["objectID"])
            rows.append(h)
    rows.sort(key=lambda h: (-(h.get("points") or 0), h["created_at_i"]))
    return [{"title": h["title"], "points": h.get("points") or 0, "created_at_i": h["created_at_i"]} for h in rows[:n]]


def handling(states: list[dict], p=HANDLING) -> dict:
    s, e = PM.bounds(p)
    rows = [i for i in states if not (i.get("author") and i["author"].get("__typename") == "Bot") and s <= PM.parse_ts(i["createdAt"]) < e]
    n = len(rows)
    if not n:
        return {"n": 0}
    closed = [i for i in rows if i.get("state") == "CLOSED" and i.get("closedAt")]
    secs = [(PM.parse_ts(i["closedAt"]) - PM.parse_ts(i["createdAt"])).total_seconds() for i in closed]
    reasons: dict[str, int] = {}
    for i in closed:
        k = i.get("stateReason") or "その他"
        reasons[k] = reasons.get(k, 0) + 1
    comments = [(i.get("comments") or {}).get("totalCount", 0) for i in rows]
    return {
        "n": n, "closed_share": len(closed) / n,
        "closed_within_7d_share": sum(1 for x in secs if x <= 7 * 86400) / n,
        "closed_within_30d_share": sum(1 for x in secs if x <= 30 * 86400) / n,
        "median_days_to_close": median(secs) / 86400 if secs else None,
        "reasons_among_closed": {k: v / len(closed) for k, v in sorted(reasons.items())} if closed else {},
        "commented_share": sum(1 for c in comments if c >= 1) / n, "median_comments": median(comments),
    }

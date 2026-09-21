"""OpenAI の公式変更履歴（data/proxies/<取得日>/changelog.html）から、項目の日付・題名・ラベルを取り出す（Q3 用。記述のみ）。

  python scripts/parse_changelog.py     # → data/proxies/<取得日>/changelog_events.json と docs/data/why_changelog_events.csv

ページの作り（2026-09-21 取得）: 項目は <li id="…" data-product="…" data-codex-topics="…"> で、中に <time>YYYY-MM-DD</time> と <h3><span>題名…。
label は data-codex-topics（codex-cli・codex-app・general など）。全項目を取り、絞り込みはしない。
"""
import csv
import html
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
raw = sorted((ROOT / "data" / "proxies").iterdir())[-1]
text = (raw / "changelog.html").read_text(encoding="utf-8", errors="replace")

items = list(re.finditer(r'<li id="([^"]+)"[^>]*?data-product="([^"]*)"[^>]*?data-codex-topics="([^"]*)"', text))
events = []
for k, m in enumerate(items):
    seg = text[m.end(): items[k + 1].start() if k + 1 < len(items) else m.end() + 20000]
    t = re.search(r"<time[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*</time>", seg)
    h = re.search(r"<h3[^>]*>\s*<span>(.*?)</span>\s*<button", seg, re.S)
    if not t or not h:
        continue
    title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h.group(1)))).strip()
    events.append({"date": t.group(1), "title": title, "label": m.group(3), "product": m.group(2), "id": m.group(1)})

events.sort(key=lambda e: (e["date"], e["id"]))
(raw / "changelog_events.json").write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")
with open(ROOT / "docs" / "data" / "why_changelog_events.csv", "w", encoding="utf-8", newline="") as fp:
    w = csv.writer(fp, lineterminator="\n")
    w.writerow(["date", "title", "label", "product"])
    w.writerows([[e["date"], e["title"], e["label"], e["product"]] for e in events])

by_month: dict[str, int] = {}
for e in events:
    by_month[e["date"][:7]] = by_month.get(e["date"][:7], 0) + 1
print(f"li 要素 {len(items)} 個 → 項目 {len(events)} 件（{events[0]['date']}〜{events[-1]['date']}）")
print("月別:", by_month)
print("label:", sorted({e["label"] for e in events}))

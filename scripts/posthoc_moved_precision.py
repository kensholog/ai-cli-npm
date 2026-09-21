"""0005 の規律 6（事後の参考。判定は変えない）: 語の規則に合った題名の無作為標本を読んで数えた結果を、割合に掛けて並べる。

  python scripts/posthoc_moved_sample.py      # 標本を作る（data/moved_samples.json、非公開。種 20260922、区分 × 期間ごとに最大 40 件）
  python scripts/posthoc_moved_precision.py   # 下の LABELS（読んで数えた件数）から docs/data/moved_precision.json を書く

数えたのは Claude（2026-09-22）。yes = 規則が意図した内容（品質: モデルの出力の質・指示に従わない・忘れる・幻覚への不満 /
利用枠・料金: 上限に当たる・消費が速い・課金の不具合への不満）、amb = どちらとも取れる、no = 無関係（例: lazy-load の機能要望、
ステータス行に利用枠を出してほしいという要望、UI の速度低下、Max plan が文脈として出るだけの不具合）。題名そのものは公開しない。
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
LABELS = {  # (yes, amb, no)
    "claude|quality": {"P0": (20, 5, 15), "P1": (27, 4, 9), "P2": (23, 7, 10)},
    "claude|model": {"P0": (37, 0, 3), "P1": (38, 0, 2), "P2": (36, 0, 4)},
    "claude|limits": {"P0": (11, 5, 24), "P1": (24, 2, 14), "P2": (22, 5, 13)},
    "codex|quality": {"P0": (5, 2, 8), "P1": (10, 3, 7), "P2": (12, 5, 13)},
    "codex|limits": {"P0": (26, 6, 8), "P1": (22, 4, 14), "P2": (19, 6, 15)},
}
MENTIONS = {  # 相手への言及は全件を読んだ
    "claude_side": {"P0": {"n": 5, "乗り換え・不利な比較": 0, "相手を手本にした機能要望": 2, "Codex プラグイン・相互運用": 2, "その他": 1},
                    "P1": {"n": 14, "乗り換え・不利な比較": 2, "相手を手本にした機能要望": 4, "Codex プラグイン・相互運用": 6, "その他": 2},
                    "P2": {"n": 22, "乗り換え・不利な比較": 5, "相手を手本にした機能要望": 6, "Codex プラグイン・相互運用": 6, "その他": 5}},
    "codex_side": {"P0": {"n": 5, "相手を手本にした機能要望": 5},
                   "P1": {"n": 9, "相手を手本にした機能要望": 6, "その他": 3},
                   "P2": {"n": 20, "相手を手本にした機能要望": 10, "Claude Code からの移行・相互運用の不具合": 7, "その他": 3}},
}

S = json.loads((ROOT / "docs" / "data" / "moved_summary.json").read_text(encoding="utf-8"))["shares_by_period"]
out = {"note": "事後の参考（0005 の規律 6）。数えたのは Claude。標本は最大 40 件で、適合率の誤差は ±15 ポイント程度。判定は変えない", "cells": {}, "mentions": MENTIONS}
for cell, by in LABELS.items():
    tool, key = cell.split("|")
    c = {}
    for p, (y, a, n) in by.items():
        tot, sh = y + a + n, S[tool][key][p]
        c[p] = {"n_match": sh["n_match"], "n_sample": tot, "yes": y, "ambiguous": a, "no": n, "precision_strict": y / tot, "precision_loose": (y + a) / tot,
                "raw_share": sh["share"], "adjusted_share_strict": sh["share"] * y / tot, "adjusted_share_loose": sh["share"] * (y + a) / tot}
    c["ratio_P1_P0"] = {k: c["P1"][f] / c["P0"][f] for k, f in (("raw", "raw_share"), ("adjusted_strict", "adjusted_share_strict"), ("adjusted_loose", "adjusted_share_loose"))}
    out["cells"][cell] = c
    print(cell, {p: (f"適合率 {c[p]['precision_strict']:.0%}", f"補正後 {c[p]['adjusted_share_strict'] * 100:.2f}%") for p in ("P0", "P1", "P2")},
          {k: round(v, 2) for k, v in c["ratio_P1_P0"].items()})
(ROOT / "docs" / "data" / "moved_precision.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

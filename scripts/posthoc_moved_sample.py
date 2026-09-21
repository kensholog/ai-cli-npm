"""0005 の規律 6: 語の規則に合った題名を無作為に取り、適合率を人手（Claude）で数えるための標本を作る。事後の参考で、判定は変えない。

  python scripts/posthoc_moved_sample.py      # data/moved_samples.json（非公開）に書く。乱数の種 20260922、区分 × 期間ごとに最大 40 件
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moved_metrics as M  # noqa: E402
import proxy_metrics as PM  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "proxies" / "2026-09-21" / "issues"
rng = random.Random(20260922)
out = {}
for tool, repo, keys in (("claude", "anthropics__claude-code", ["quality", "model", "limits", "other_from_claude"]),
                         ("codex", "openai__codex", ["quality", "limits", "other_from_codex"])):
    issues = PM.human_issues(PM.load_jsonl(RAW / f"{repo}.jsonl"))
    for key in keys:
        for pname, per in M.PERIODS.items():
            rows = sorted((i for i in issues if M.in_any(i, (per,)) and M.matcher(key)(i)), key=lambda i: i["number"])
            pick = rows if len(rows) <= 40 else rng.sample(rows, 40)
            out[f"{tool}|{key}|{pname}"] = {"n_match": len(rows), "sample": [{"number": i["number"], "title": i["title"]} for i in sorted(pick, key=lambda i: i["number"])]}
(ROOT / "data" / "moved_samples.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print({k: (v["n_match"], len(v["sample"])) for k, v in out.items()})

"""Step 0: measure SWE-PRBench diff sizes to ground the per-review cost estimate.

Reads data only; makes no model calls. Token counts here are a chars/4 approximation,
not tokenizer output; Step 1 replaces them with provider-reported usage.
"""
import json
import statistics
import sys
from pathlib import Path

root = Path(sys.argv[1])
prs = [json.loads(line) for line in (root / "prs.jsonl").read_text().splitlines() if line.strip()]
split = json.loads((root / "evals" / "eval_100.json").read_text())


def ids_from(obj):
    if isinstance(obj, dict):
        for key in ("task_ids", "tasks", "prs", "ids"):
            if key in obj:
                return ids_from(obj[key])
        return list(obj)
    return [x["task_id"] if isinstance(x, dict) else x for x in obj]


eval_ids = set(ids_from(split))


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))]


def summarize(name, rows):
    chars = [len(r.get("diff_patch") or "") for r in rows]
    comments = [r.get("num_substantive_comments") or 0 for r in rows]
    out = {
        "set": name,
        "n": len(rows),
        "diff_chars_p50": pct(chars, 0.5),
        "diff_chars_p90": pct(chars, 0.9),
        "diff_chars_max": max(chars),
        "diff_chars_mean": round(statistics.mean(chars)),
        "approx_tokens_p50": pct(chars, 0.5) // 4,
        "approx_tokens_p90": pct(chars, 0.9) // 4,
        "approx_tokens_mean": round(statistics.mean(chars)) // 4,
        "approx_tokens_max": max(chars) // 4,
        "over_32k_approx_tokens": sum(c // 4 > 32000 for c in chars),
        "human_comments_mean": round(statistics.mean(comments), 2),
        "human_comments_total": sum(comments),
    }
    return out


report = {
    "keys": sorted(prs[0].keys()),
    "split_type": type(split).__name__,
    "split_keys": sorted(split.keys()) if isinstance(split, dict) else None,
    "eval_ids": len(eval_ids),
    "all": summarize("all_350", prs),
    "eval_100": summarize("eval_100", [r for r in prs if r["task_id"] in eval_ids]),
    "languages": {},
    "difficulty": {},
}
for r in prs:
    report["languages"][r.get("language")] = report["languages"].get(r.get("language"), 0) + 1
    report["difficulty"][r.get("difficulty")] = report["difficulty"].get(r.get("difficulty"), 0) + 1
print(json.dumps(report, indent=2))

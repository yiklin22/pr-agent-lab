# Step 0 sources (all read on 2026-11-12)

| What | Where | Pinned at |
|---|---|---|
| PR-Agent | https://github.com/The-PR-Agent/pr-agent | commit `41a7ead8` (`v0.50.0-100-g41a7ead8`), cloned to `upstream/pr-agent` |
| SWE-PRBench harness | https://github.com/FoundryHQ-AI/swe-prbench | commit `379f0bf` (2026-03-30), cloned to `upstream/swe-prbench` |
| SWE-PRBench dataset | https://huggingface.co/datasets/foundry-ai/swe-prbench | revision `b87f5797aef3ed2c3153bb1304ea4d801d36ba6e`; `prs.jsonl` and `evals/eval_100.json` in `data/swe-prbench/dataset` |
| ReviewBench | https://github.com/review-bench/ReviewBench | commit `f223ce3` (2026-11-05), cloned to `upstream/ReviewBench` |
| LiteLLM price table | https://raw.githubusercontent.com/BerriAI/litellm/v1.108.5/model_prices_and_context_window.json | tag `v1.108.5` (the version PR-Agent pins) |

`upstream/` and `data/swe-prbench/` are git-ignored; re-create them from the pins above.

Files in this folder:
- `open_issues.json`, `open_prs.json`: `gh issue list` / `gh pr list` output for PR-Agent.
- `swe_prbench_diff_sizes.json`: output of `scripts/step0_diff_sizes.py`.
- `reviewer_prompt_sizes.json`: character counts of the `/review` prompt templates.
- `litellm_prices_v1.108.5_extract.json`: price rows for the candidate models.

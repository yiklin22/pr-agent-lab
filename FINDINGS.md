# Step 0 findings: PR-Agent, benchmarks, model and cost

Read on 2026-11-12. No PR-Agent code was changed and no model was called. Pins for everything read are in
`data/step0/SOURCES.md`. Paths starting with `upstream/` are local checkouts (git-ignored).

## Summary

- **License is MIT**, not Apache 2.0. The Apache claim was true for seven weeks in mid-2026.
- **No written AI-contribution policy.** AI-assisted PRs are common and are disclosed in practice.
- **LiteLLM is confirmed.** Prompt-cache breakpoints exist but are **off by default**.
- **No eval harness and no benchmark results** exist upstream. This is the clearest gap the project fills.
- **Three of your planned steps overlap work already open upstream** (confidence threshold, cache fix,
  comment-argument hardening). Details in section 5.
- **Recommended benchmark: SWE-PRBench.** ReviewBench is usable under MIT, but its ground truth is 98%
  machine-produced and it needs Docker and Node, which this machine lacks.
- **Recommended review model: `claude-sonnet-5-5`,** projected at roughly US$0.03 to $0.08 per review. That is
  arithmetic from list prices, not a measurement.
- **A stock CLI run posts to the PR by default.** Step 1 must be set up so posting is impossible, not just
  switched off.

## 1. License

| Fact | Evidence |
|---|---|
| Current license is MIT, copyright "2026 The PR Agent" | `upstream/pr-agent/LICENSE`; GitHub API reports `MIT` |
| Apache 2.0 at the 2023 release | commit `4b4d91df` |
| Changed to AGPL-3.0 on 2025-05-22 | commit `70428ebb` |
| Changed back to Apache 2.0 on 2026-05-20 | commit `fdbcecc8` ("From GNU AGPL v3.0 to Apache License 2.0") |
| Changed to MIT on 2026-07-09 | commit `d7e94bc2` ("From Apache-2.0 to MIT") |

Both of your sources were right for their date. One leftover: `tests/unittest/test_git_provider_head_sha.py`
still carries an `SPDX-License-Identifier: Apache-2.0` header. Neither `CONTRIBUTING.md` nor `AGENTS.md`
mentions a CLA or a DCO sign-off.

Other facts in the brief that I checked:

| Brief said | Found |
|---|---|
| 13.6k stars | 15,980 stars, 2,182 forks (GitHub API) |
| Community-owned since April 2026 | README confirms the donation and names one external maintainer; it says the move to a foundation is still "in process". I did not verify the April date. |
| `/help_docs` is off pending a credential fix | Confirmed: disabled since v0.36.1 for issue #2445; the fix, PR #2450, has been open since 2026-06-16 |
| Runs as Action, CLI, Docker, webhooks | Confirmed (`pr_agent/servers/`, `action.yaml`, `pr_agent/cli.py`) |

The project moves fast: 6,500 commits, release v0.50.0 on 2026-11-07, about one release every two weeks, and
100 commits on `main` in the five days since. 23 PRs and 13 issues are open.

## 2. What contributors must do

**CONTRIBUTING.md** (`upstream/pr-agent/CONTRIBUTING.md`):

- Fork, use `uv` and Python 3.12 or newer, install with `uv sync`.
- Branch as `feature/<name>` or `fix/<issue>`.
- Run `PYTHONPATH=. uv run pytest tests/unittest`.
- Run `uv run ruff check --fix <changed files>` and `uvx pre-commit run --files <changed files>`.
- Conventional commit messages, one feature or fix per PR, unit tests for new behaviour, docs updated, issue linked.

**AGENTS.md** adds rules that a reviewer will hold a PR to:

- 120-character lines, no repo-wide reformatting, match the surrounding style.
- Settings go in `pr_agent/settings/configuration.toml`. The config reference page is generated from it, and a
  test asserts a hard-coded count of active keys, so a new setting means updating that count.
- New prompt files must be registered in `pr_agent/config_loader.py`.
- Ask before adding dependencies, renaming files, or changing workflows.
- A fix in one git provider or server usually has to be applied to its siblings, or the PR must name them.
- New regexes must run in linear time.

**Security policy** (`SECURITY.md`): report privately through GitHub's private vulnerability reporting
(`/security/advisories/new`). It says explicitly not to open a public issue. This matches your rule for Step 5.

**AI-assisted contributions:** there is no written policy. Evidence of practice:

- `AGENTS.md` is written as instructions for coding agents.
- Open PR #4394 and closed PR #4221 end with "Generated with Claude Code".
- 40 AI co-author or "generated with" trailer lines appear in the last 300 commit bodies.

So AI help is accepted, and disclosing it is the norm. I recommend you disclose it in your PRs.

## 3. How it calls models

- **LiteLLM, confirmed.** `litellm==1.108.5` is pinned in `pyproject.toml`. The default handler is
  `pr_agent/algo/ai_handlers/litellm_ai_handler.py` (3,841 lines). LangChain and plain-OpenAI handlers also exist.
- **Default model** is `gpt-6.1-sol` with fallback `gpt-6-luna` (`configuration.toml:9-10`).
- **One call per `/review`** unless large-PR chunking is switched on (off by default, up to 3 calls).
- `max_model_tokens = 32000` caps the prompt of any single call.

**Prompt caching:**

| Question | Answer | Evidence |
|---|---|---|
| Does it set cache breakpoints? | Only if the operator opts in. Default is `cache_control_injection_points = []`. | `configuration.toml:548-556` |
| Which models? | Claude only. Other models get a one-time warning. | `litellm_ai_handler.py:2827-2869` |
| Where does the breakpoint land? | End of the system message. With skills configured, the system prompt is split so the shared skills block gets its own breakpoint. | `litellm_ai_handler.py:2777-2824` |
| Is cache use measured? | Yes. Cache-read and cache-write tokens are summed per run, shown in the optional run-details footer, and exported as OpenTelemetry counters. | `pr_agent/algo/run_details.py`, `pr_agent/agent/pr_agent.py:220-240` |
| Known weak spots | Parallel chunk calls each write their own cache entry (issue #4876, fix in open PR #4877). | GitHub |
| Is the `/review` prefix the same across PRs? | Yes, with default settings. The rendered system prompt was byte-identical (7,065 characters, same SHA-256) for three different PRs. `num_pr_files` is rendered only when `require_can_be_split_review` is on, and it is off by default. | `runs/step1-stub/captured_requests/`. **Corrected in Step 1:** my Step 0 reading of the template said the prefix varied per PR, and that was wrong. |

So with default settings there is no prefix bug to fix in `/review`. The cacheable prefix is also small: about
1,800 tokens at four characters per token.

## 4. Existing evaluation harness or benchmark results

None.

- No file in the repository matches bench, eval, golden, fixture or dataset, except
  `pr_agent/settings/pr_evaluate_prompt_response.toml`, a prompt for comparing two responses. I did not trace
  where it is used.
- The docs contain no benchmark, precision or recall figures.
- Tests are unit, end-to-end and health checks. They test plumbing, not review quality.
- Open PR #4394 says in its own test plan: "confidence calibration is untested on real PRs".
- Old requests for benchmarks (#884, #1084) were closed without one being built.

## 5. Open issues and PRs that overlap your steps

Full lists are saved in `data/step0/open_issues.json` and `data/step0/open_prs.json`.

| Your step | Upstream item | State | What it means for you |
|---|---|---|---|
| 4 Noise | PR #4394: each finding carries a model-reported 0-10 confidence, plus `pr_reviewer.min_finding_confidence` | Open, review required | The threshold knob is being added by someone else. Nobody has shown what value to set it to. Your certified threshold is the missing evidence, so build on this PR and do not duplicate it. |
| 4 Noise | Already merged: `num_max_findings = 6`, persistent finding state, inline-comment dedup, earlier-finding context | On `main` | The stock baseline is already capped at 6 findings per review. Precision gains have to come from within those 6. |
| 5 Injection | Issue #4444: 248 of 296 config keys can be set by anyone who can comment `/command --section.key=value`; commenter identity is never checked | Open, labelled `breaking`, being worked on in pieces | This is your "review-command arguments" surface. Attacks here will mostly rediscover #4444. Check each success against it before treating it as new. |
| 5 Injection | Issues #3917, #3972 (closed): "treat as untrusted data" sentences added to prompts | Merged | The current defence for title, body, diff and commit messages is prompt wording plus markers. That is the gap your "fixes in code, not prompts" rule targets. |
| 5 Injection | PR #2450: clone-host validation, restores nothing yet | Open since June | Already public. Not a new finding if you hit it. |
| 6 Cost | Issue #4876 and PR #4877: stagger the first chunk so siblings read the cache | Open, opened today | Taken. Do not redo it. |
| 6 Cost | Closed: #2601 (breakpoint placement RFC), #3610 ("caching is configured blind"), #3836 | Merged | Most of the plumbing you planned to add exists. What is missing is measured hit rates on real reviews. |
| 3 Operate | `[otel]` section, Prometheus exporter, `output_run_details`, `output_run_cost`, `[push_outputs]` file sink, `github_polling.py` server | On `main` | Tokens, cache tokens, cost, latency and failures are already collected per run. Step 3 shrinks to configuration, a report script, and whatever is missing. |

## 6. Benchmarks

### SWE-PRBench

- **Harness is published:** `github.com/FoundryHQ-AI/swe-prbench`, MIT, Python, 4,600 lines, last pushed 2026-03-30.
- **Dataset:** `foundry-ai/swe-prbench`, CC BY 4.0, not gated. 350 PRs from 65 repos.
- **Ground truth:** comments human reviewers left on merged PRs, 2,240 in total.
- **Languages:** Python 242, JavaScript 37, Go 35, TypeScript 21, Java 15 (`data/step0/swe_prbench_diff_sizes.json`).
- **Matcher and judge exist:** `eval_harness/judge.py`, `matching.py`, `scorer.py`, with a frozen rubric
  (`RUBRIC.md`) that labels each tool comment CONFIRMED, PLAUSIBLE or FABRICATED.
- **Runs on this machine:** needs only Python.

Limits you should know before relying on it:

- **The harness cannot score an outside tool as shipped.** `run_eval.py` always calls a model with its own
  prompt. Scoring PR-Agent needs a small adapter: run PR-Agent on each `diff_patch`, convert its findings to the
  harness's `AgentOutput` shape, then call the harness's judge and scorer.
- **Its "precision" is strict.** `scorer.py` computes `confirmed / total comments`, so a correct comment that no
  human happened to make (PLAUSIBLE) counts against precision. The separate fabricated rate measures wrong comments.
- **The paper's judge is GPT-5.2,** which needs an OpenAI key. Reported judge agreement is kappa 0.75.
- **Our numbers will not be comparable to its leaderboard.** That table scores raw models on the harness's
  prompt and prepared context, not a tool with its own prompt.
- **Small project:** one author, 9 stars, no commits since March.
- **The paper's 100-PR split has smaller diffs than the rest:** mean about 3,500 tokens against 14,500 for all
  350, and one PR in the full set has a 13 MB diff. Token figures are characters divided by 4.

### ReviewBench (GitHub)

- **Usable under its license:** MIT, `github.com/review-bench/ReviewBench`, 219 PRs, 187 repos, 19 languages,
  actively maintained (last commit 2026-11-05), with a public leaderboard. PR-Agent is not registered on it.
- **Ground truth is mostly machine-produced.** Of 2,623 true-positive findings, 53.0% came from LLM review
  agents, 45.2% from `ccr`, and 1.5% from human review comments (README, "Finding Producers"). Humans audited
  the labels, but they did not write the findings.
- **Needs Docker to run a reviewer and Node to run the judge.** This machine has neither.
- **Offline scores cannot be published as leaderboard results.** A leaderboard entry needs a container image
  submitted through their portal.

### Recommendation

Use **SWE-PRBench as the primary benchmark.** Your success line says "recall against human-flagged issues", and
only SWE-PRBench measures that. It also runs here, and 350 PRs is enough to split into calibration and test.

Keep ReviewBench as an optional second benchmark for later. It would need a machine or CI runner with Docker.
A leaderboard entry for PR-Agent would be a visible result, but it is extra scope.

## 7. Model and cost per review

No API key for any model provider is set on this machine, so nothing below is measured.

**Prices** (LiteLLM v1.108.5 table, the one PR-Agent uses to compute cost; saved in
`data/step0/litellm_prices_v1.108.5_extract.json`):

| Model | Input $/MTok | Output $/MTok | Cache write | Cache read | Min cacheable prefix |
|---|---|---|---|---|---|
| `claude-opus-5-5` | 4.00 | 20.00 | 5.00 | 0.20 | 512 tokens |
| `claude-sonnet-5-5` | 2.00 | 10.00 | 2.50 | 0.10 | 512 tokens |
| `claude-haiku-5-5` | 0.10 | 0.50 | 0.125 | 0.01 | 512 tokens |
| `gpt-6.1-sol` (PR-Agent default) | 2.00 | 10.00 | 2.50 | 0.10 | not listed |

**Recommendation: `anthropic/claude-sonnet-5-5`.**

- Step 6 needs a Claude model, because PR-Agent only forwards cache breakpoints for Claude.
- It costs the same per token as PR-Agent's default, so cost figures describe what a typical operator pays.
- The `/review` system prompt template is about 4,300 tokens, above the 512-token cache minimum.
- Opus 5.5 would double the cost and Haiku 5.5 would cut it to about a twentieth. Which tier to use is your call.
  A Haiku arm would be a cheap comparison later.

**Projected cost of one review on Sonnet 5.5:**

| Part | Assumption | Cost |
|---|---|---|
| Input, median benchmark PR | about 8,000 tokens: system template up to 4,300, user framing up to 1,400, diff 2,200 | $0.016 |
| Input, 90th-percentile benchmark PR | about 14,000 tokens (diff 8,600) | $0.029 |
| Input, hard ceiling per call | 32,000 tokens (`max_model_tokens`) | $0.064 |
| Output | 1,500 to 4,000 tokens including thinking; **a guess, nothing here measures it** | $0.015 to $0.040 |
| **Total** | | **about $0.03 to $0.08** |

Caveats: token counts are characters divided by 4, and the current Claude tokenizer can produce up to about 1.35
times more. Reviews of live PRs carry extra context (surrounding lines, `AGENTS.md`, commit messages), so they
sit nearer the ceiling. Step 1 replaces all of this with provider-reported usage.

On these figures, 100 benchmark reviews cost about $3 to $8 before judge calls. The judge cost is unknown until
the Step 2 pilot.

## What failed or is unverified

- The April 2026 donation date: the history search hung on the partial clone, so I stopped it.
- Whether `publish_output=false` blocks every write. It is checked at more than a dozen separate places in
  `pr_reviewer.py` and not in the GitHub provider, so I would not rely on it alone.
- Resolved in Step 1: `--json-output` carries prompt, completion and total tokens, but not cache tokens, cost
  or duration.
- Resolved in Step 1: `num_pr_files` does not defeat the cache with default settings (section 3).
- The Kudelski Security `/ask` finding from the brief: not checked.
- ReviewBench and SWE-PRBench were read, not run.

## Revised plan

Changes to the steps in the brief. Unlisted steps stand as written.

**Step 1 (Reproduce): add a no-posting guarantee and an API key.**
- A stock `pr-agent --pr_url ... review` publishes a comment. Your `gh` token has `repo` scope, so it could post
  to any public PR.
- Run with no GitHub token, or a read-only fine-grained token, so posting fails in code. Also set
  `config.publish_output=false` and use `--json-output`.
- You need to provide an Anthropic API key. Three reviews are projected at well under $1.
- Find out in this step where tokens, cost and latency can be read from a CLI run.

**Step 2 (Baseline): write an adapter, and settle three choices at the pilot.**
- Build the PR-Agent to SWE-PRBench adapter, reusing the benchmark's judge and scorer unchanged.
- Judge model: GPT-5.2 as in the paper (needs an OpenAI key) or a Claude judge. The reviewer model should not
  judge itself.
- Split: the paper's 100 as test and the other 250 as calibration, or a seeded random split of all 350. The
  size difference noted above matters for Step 4, because Learn-then-Test assumes calibration and test PRs come
  from the same distribution.
- Report precision two ways: the benchmark's strict figure, and the fabricated rate.

**Step 3 (Operate): smaller than planned.**
- Use the existing run details, OpenTelemetry counters and file sink before writing any logging.
- No Docker here, so deploy as a GitHub Action on your repos. `fieldgate` has no GitHub remote and cannot be
  included until you push it.
- Shadow mode uses the same no-posting setup as Step 1.

**Step 4 (Noise): position against PR #4394.**
- Treat its model-reported confidence as one signal among yours, and aim the upstream contribution at "here is
  a calibrated value for `min_finding_confidence`, with evidence".
- Decide what a "bad comment" is before calibrating: fabricated only, or anything not confirmed by a human.

**Step 5 (Injection): check every success against issue #4444 and PR #2450** before calling it new.

**Step 6 (Cost): the question changes** from "add breakpoints" to "measure hit rates, then fix placement". The
chunk case is taken by PR #4877, and the `/review` prefix is already stable (section 3). This step may find
little to fix; its likely output is measured hit rates and a recommendation on the default.

**Step 7 (Upstream): expect competition.** Issues are claimed within hours. You would need to comment on an
issue to claim it before I draft the PR, since I do not post upstream.

## Step 1 rehearsal update (2026-11-12, no API key)

No model has been called yet. These are measurements of PR-Agent itself, taken by pointing it at a local
stand-in (`scripts/stub_llm.py`) that records each request. Logs: `runs/step1-stub/`.

**Real prompt sizes for the three chosen PRs** (`runs/step1-stub/summary.json`, `captured_prompts`):

| PR | Diff | System prompt | User prompt | Total characters | Characters / 4 |
|---|---|---|---|---|---|
| coreos/coreos-assembler#4394 (Go) | 2 files | 7,065 | 1,279 | 8,344 | 2,086 |
| falconry/falcon#2540 (Python) | 3 files | 7,065 | 12,078 | 19,143 | 4,785 |
| firebase/firebase-android-sdk#7617 (Java) | 10 files | 7,065 | 41,755 | 48,820 | 12,205 |

The section 7 projection assumed a 4,300-token system prompt. The rendered one is about 1,800 at the same
characters-per-token rate, so the input side of a small review is cheaper than projected. Real token counts
still need a model call.

**Other things the rehearsal established:**

- Plain-diff mode needs no GitHub access at all. All three runs also completed inside a network namespace with
  no route out (`runs/step1-stub-nonetwork/`).
- The GitHub provider cannot run without a token (`github_provider.py`, `_get_github_client`), so "no token"
  is not an option on the `--pr_url` path. Plain-diff mode is the no-posting route.
- PR-Agent's own cost line rounds to whole cents ("$0.04", "<$0.01"). Per-review cost is therefore computed in
  `scripts/step1_run.py` from token counts and the pinned price table.
- For an unknown OpenAI-style model the request carries only `model`, `messages` and `temperature`. What it
  sends for Claude is not yet observed.
- CLI start-up costs about 4.5 seconds per run before any model time. PR-Agent's own "Time cost" excludes it.

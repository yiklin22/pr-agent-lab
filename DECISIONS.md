# Decisions

One entry per real choice: what was chosen, what was rejected, and why. Entries marked **proposed** are
recommendations waiting for your answer.

## Step 0

### D1. Keep this work in its own repository, with upstream code checked out beside it
**Chose:** `pr-agent-lab/` holds findings, scripts, logs and results; PR-Agent and the benchmarks are cloned
under `upstream/` and git-ignored, pinned by commit in `data/step0/SOURCES.md`.
**Rejected:** working inside a fork of PR-Agent. A fork should contain only what could go upstream, and
benchmark logs, cost data and attack results must never land in an upstream PR by accident.
**Later:** code changes to PR-Agent will go in a fork of `The-PR-Agent/pr-agent`, one branch per contribution.

### D2. Primary benchmark: SWE-PRBench (proposed)
**Chose:** SWE-PRBench, because its ground truth is comments written by human reviewers, which is what "recall
against human-flagged issues" means, and because it runs on this machine with Python alone.
**Rejected as primary:** ReviewBench. Its license is fine (MIT), but 98% of its true-positive findings were
produced by LLM reviewers or `ccr` and only 1.5% by human review comments, and it needs Docker and Node.
**Cost of the choice:** SWE-PRBench is a one-author project with no commits since March 2026, and its harness
needs an adapter to score an outside tool.

### D3. Review model: `claude-sonnet-5-5` (proposed)
**Chose:** Sonnet 5.5 through LiteLLM. PR-Agent forwards cache breakpoints only for Claude models, which Step 6
depends on, and Sonnet 5.5 is priced the same as PR-Agent's default model ($2 in, $10 out per million tokens),
so cost results describe a typical deployment.
**Rejected:** the stock default `gpt-6.1-sol` (no cache-breakpoint path in PR-Agent), Opus 5.5 (twice the
price), Haiku 5.5 (a twentieth of the price, but a weaker reviewer would understate the baseline).
**Open:** the tier is your decision; this is a recommendation on cost and fit.

### D4. Reviews of other people's PRs must be unable to post, not merely told not to (proposed)
**Chose:** run with no GitHub token or a read-only one, in addition to `config.publish_output=false`.
**Rejected:** relying on `publish_output=false` alone. It is checked at more than a dozen separate call sites in
`pr_reviewer.py` and not inside the GitHub provider, so one unguarded path would post to a stranger's PR.
**Why it matters:** the local `gh` token has `repo` scope, and "never post to repos I do not own" is a hard rule.

### D5. Cost figures before Step 1 are labelled projections
**Chose:** report per-review cost as arithmetic from list prices and measured character counts, with the
output-token assumption called out as a guess.
**Rejected:** quoting a single dollar figure. No model has been called, so any single number would be invented.

## Interview questions for Step 0

**Q1. Why did you measure on SWE-PRBench instead of GitHub's ReviewBench, which is bigger-name and newer?**
I wanted to measure agreement with human reviewers. SWE-PRBench's ground truth is the comments humans left on
merged PRs. ReviewBench's golden set is human-audited, but its README shows 53.0% of true positives came from
LLM review agents, 45.2% from `ccr`, and 1.5% from human review comments. Scoring an LLM reviewer against
findings mostly produced by LLM reviewers measures something different. The trade-off I accepted is a smaller,
less maintained benchmark whose "precision" penalises correct comments that no human happened to make, so I
report the fabricated rate alongside it.

**Q2. PR-Agent already supported prompt caching. What was left for you to do?**
Support and benefit are different things. The breakpoints are off by default
(`cache_control_injection_points = []`) and only apply to Claude models, and nobody had published hit rates on
real reviews. I first read the template and concluded the `/review` prefix changed with every PR because it
interpolates `num_pr_files`. Capturing the real requests showed that was wrong: the variable sits inside an
option that is off by default, and the system prompt was byte-identical across three PRs. I keep that in the
record because it is why I measure before proposing a fix.
*(Update this answer after Step 6 with the measured hit rates.)*

**Q3. How did you make sure your experiments never commented on a stranger's pull request?**
PR-Agent's CLI publishes by default, and its "do not publish" flag is enforced at many separate call sites in
the review command, not at the provider. A flag checked in more than a dozen places is a convention, not a guarantee. So I
removed the capability: reviews of public PRs ran without a token that could write, which makes a missed check
fail with a permission error instead of posting.
*(Update after Step 1 with the exact setup used.)*

## Step 1 (keyless part, 2026-11-12)

Step 1 is not finished: no model has been called. These decisions cover the setup and the rehearsal.

### D6. The three PRs: one small, one medium, one large, from benchmark repositories
**Chose:** coreos/coreos-assembler#4394 (Go, 2 files), falconry/falcon#2540 (Python, 3 files) and
firebase/firebase-android-sdk#7617 (Java, 10 files), near the 10th, 50th and 90th percentile of diff size in
SWE-PRBench's 100-PR split.
**Rejected:** PR-Agent's own PRs (already reviewed by a bot, and circular), and freshly opened PRs (no human
review to compare against yet).
**Cost of the choice:** all three merged in December 2025, so a model may have seen them in training.

### D7. Run in plain-diff mode, not `--pr_url`
**Chose:** fetch each PR's diff, title and description anonymously, then run `pr-agent --diff-file`. PR-Agent
then has no git provider and nothing to post to. All three rehearsal runs completed with the network removed.
**Rejected:** `--pr_url` with the GitHub provider. It refuses to start without a token, and the only token on
this machine can write. A read-only token would make that path safe, and you would have to create it.
**Cost of the choice:** the model sees only the diff, title and description. It does not get surrounding code,
commit messages or linked tickets, so these reviews see less than a deployed instance would. This is the same
mode the Step 2 benchmark will use.

### D8. Rehearse against a local HTTP stand-in, not an in-process fake
**Chose:** a small local server that speaks the chat-completions protocol, so the rehearsal uses the same CLI
command and the same LiteLLM path as the live run, and saves the exact request.
**Rejected:** injecting a fake handler in Python, as upstream's smoke test does. It skips LiteLLM and the
usage accounting, which are the parts most likely to surprise the live run.
**Rule:** everything the stand-in returns is marked `"stub": true` and is never reported as a result.

### D9. Compute cost from tokens, not from PR-Agent's footer
**Chose:** tokens from `--json-output` multiplied by the pinned LiteLLM prices.
**Rejected:** PR-Agent's "Estimated API cost" line, which rounds to whole cents and would turn a $0.034 review
into "$0.03". Limit: the JSON has no cache-token fields, so this is exact only while caching is off.

"""Step 1: run stock PR-Agent from its CLI on public pull requests and record what happened.

How posting is made impossible (DECISIONS.md D4):
  * The PR is fetched here, anonymously, as a plain diff plus title and description.
  * PR-Agent runs in plain-diff mode (--diff-file). It has no git provider and no PR URL.
  * Every GitHub credential is removed from the child process environment.

Two modes:
  --mode stub   No API key. PR-Agent talks to scripts/stub_llm.py on localhost. This rehearses the
                pipeline and captures the real prompts. Records are marked "stub": true and carry
                no model results.
  --mode live   A real model through LiteLLM. Needs the provider key in the environment.

Usage:
  python scripts/step1_run.py --mode stub --out runs/step1-stub
  python scripts/step1_run.py --mode live --model anthropic/claude-sonnet-5-5 --out runs/step1-live
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
PR_AGENT = LAB / "upstream" / "pr-agent"
PR_AGENT_CLI = PR_AGENT / ".venv" / "bin" / "pr-agent"
PR_AGENT_PYTHON = PR_AGENT / ".venv" / "bin" / "python"
PRICE_TABLE = LAB / "data" / "step0" / "litellm_prices_v1.108.5_extract.json"

# Three public PRs from repositories in SWE-PRBench's 100-PR split: small, medium and large diffs,
# three languages. Chosen in Step 1; see DECISIONS.md D6.
DEFAULT_PRS = [
    "https://github.com/coreos/coreos-assembler/pull/4394",
    "https://github.com/falconry/falcon/pull/2540",
    "https://github.com/firebase/firebase-android-sdk/pull/7617",
]

# Credentials that could let a child process write to GitHub. Removed before PR-Agent starts.
GITHUB_ENV = ("GITHUB_TOKEN", "GH_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB__USER_TOKEN", "GITHUB.USER_TOKEN")
# Provider keys that live mode may pass through to PR-Agent, mapped to PR-Agent's setting names.
PROVIDER_KEYS = {"ANTHROPIC_API_KEY": "ANTHROPIC__KEY", "OPENAI_API_KEY": "OPENAI__KEY"}
USER_AGENT = "pr-review-research-script"


def http_get(url: str, accept: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https hosts
        return response.read()


def fetch_pr(pr_url: str, inputs_dir: Path) -> dict:
    """Download one PR's diff and metadata without credentials. Cached on disk."""
    match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not match:
        raise ValueError(f"Not a GitHub PR URL: {pr_url}")
    owner, repo, number = match.groups()
    slug = f"{owner}__{repo}__{number}"
    meta_path, diff_path = inputs_dir / f"{slug}.json", inputs_dir / f"{slug}.diff"
    if not (meta_path.exists() and diff_path.exists()):
        api = json.loads(http_get(f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
                                  "application/vnd.github+json"))
        diff = http_get(f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
                        "application/vnd.github.diff")
        meta = {
            "pr_url": pr_url,
            "slug": slug,
            "title": api.get("title") or "",
            "description": api.get("body") or "",
            "state": api.get("state"),
            "merged_at": api.get("merged_at"),
            "base_sha": api["base"]["sha"],
            "head_sha": api["head"]["sha"],
            "changed_files": api.get("changed_files"),
            "additions": api.get("additions"),
            "deletions": api.get("deletions"),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fetched_with_credentials": False,
        }
        diff_path.write_bytes(diff)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["diff_path"] = str(diff_path)
    meta["diff_chars"] = len(diff_path.read_text(encoding="utf-8", errors="replace"))
    return meta


def versions() -> dict:
    def run(*cmd, cwd=None):
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False).stdout.strip()

    probe = "import importlib.metadata as m; print(m.version('litellm')); print(m.version('pr-agent'))"
    litellm_version, package_version = (run(str(PR_AGENT_PYTHON), "-c", probe).splitlines() + ["", ""])[:2]
    return {
        "pr_agent_commit": run("git", "rev-parse", "HEAD", cwd=PR_AGENT),
        "pr_agent_describe": run("git", "describe", "--tags", cwd=PR_AGENT),
        "pr_agent_package_version": package_version,
        "pr_agent_local_changes": bool(run("git", "status", "--porcelain", "--untracked-files=no", cwd=PR_AGENT)),
        "litellm_version": litellm_version,
    }


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def child_env(mode: str, model: str, stub_port: int | None) -> tuple[dict, list[str]]:
    env = {k: v for k, v in os.environ.items() if k not in GITHUB_ENV and k not in PROVIDER_KEYS}
    removed = [k for k in GITHUB_ENV if k in os.environ]
    env["GH_CONFIG_DIR"] = "/nonexistent"  # the gh CLI's stored login is not reachable from the child
    env["CONFIG__FALLBACK_MODELS"] = "[]"  # a fallback model would blur which model produced the review
    env["CONFIG__OUTPUT_RUN_DETAILS"] = "true"
    env["CONFIG__OUTPUT_RUN_COST"] = "true"
    env["CONFIG__MODEL"] = model
    if mode == "stub":
        env["OPENAI__KEY"] = "stub-not-a-key"
        env["OPENAI__API_BASE"] = f"http://127.0.0.1:{stub_port}/v1"
        env["CONFIG__CUSTOM_MODEL_MAX_TOKENS"] = "32000"
    else:
        passed = [name for name in PROVIDER_KEYS if os.environ.get(name)]
        if not passed:
            raise SystemExit("live mode needs a provider key in the environment, e.g. ANTHROPIC_API_KEY")
        for name in passed:
            env[name] = os.environ[name]
            env[PROVIDER_KEYS[name]] = os.environ[name]
    return env, removed


def parse_run_details(markdown: str) -> dict:
    """Read PR-Agent's own "Agent run details" footer: the lines after its heading, as written."""
    marker = markdown.rfind("Agent run details")
    if marker == -1:
        return {}
    details = {}
    for line in markdown[marker:].splitlines():
        match = re.match(r"\s*- ([^:]+): (.+)", line)
        if match:
            details[match.group(1).strip()] = match.group(2).strip()
    seconds = re.match(r"([\d.]+)s", details.get("Time cost", ""))
    if seconds:
        details["model_seconds"] = float(seconds.group(1))
    cost = re.match(r"\$?([\d.]+) USD", details.get("Estimated API cost", ""))
    if cost:
        details["cost_usd"] = float(cost.group(1))
    return details


def computed_cost(model: str, usage: dict) -> dict:
    """Price a run from its token counts and the pinned LiteLLM price table.

    PR-Agent's footer rounds cost to whole cents ("$0.04", "<$0.01"), which is too coarse for a
    per-review figure. This is exact only while prompt caching is off, because --json-output
    does not report cache tokens.
    """
    prices = json.loads(PRICE_TABLE.read_text(encoding="utf-8"))["models"]
    row = prices.get(model.split("/")[-1])
    if not row or not usage.get("prompt_tokens"):
        return {"cost_usd": None, "reason": "model not in the pinned price table or no usage reported"}
    cost = (usage["prompt_tokens"] * row["input_cost_per_token"]
            + usage.get("completion_tokens", 0) * row["output_cost_per_token"])
    return {"cost_usd": round(cost, 6), "price_table": PRICE_TABLE.name, "assumes": "no prompt-cache reads or writes"}


def run_one(meta: dict, mode: str, model: str, out_dir: Path, stub_port: int | None) -> dict:
    run_dir = out_dir / meta["slug"]
    run_dir.mkdir(parents=True, exist_ok=True)
    json_out, md_out = run_dir / "review.json", run_dir / "review.md"
    for stale in (json_out, md_out):
        stale.unlink(missing_ok=True)
    env, removed = child_env(mode, model, stub_port)
    command = [
        str(PR_AGENT_CLI),
        "--diff-file", meta["diff_path"],
        "--output", str(md_out),
        "--json-output", str(json_out),
        "review",
        f"--plain_diff.title={meta['title']}",
        f"--plain_diff.description={meta['description']}",
    ]
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    start = time.monotonic()
    # cwd is the empty run directory, so PR-Agent finds no working tree and sees only the diff.
    result = subprocess.run(command, cwd=run_dir, env=env, capture_output=True, text=True, timeout=900, check=False)
    wall_seconds = round(time.monotonic() - start, 2)
    (run_dir / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")

    review = json.loads(json_out.read_text(encoding="utf-8")) if json_out.exists() else {}
    usage = review.get("usage") or {}
    # --json-output carries only prompt/completion/total tokens. Model, cache tokens, model time
    # and cost appear only in the Markdown "Agent run details" footer, so read them from there.
    run_details = parse_run_details(md_out.read_text(encoding="utf-8") if md_out.exists() else "")
    record = {
        "pr_url": meta["pr_url"],
        "head_sha": meta["head_sha"],
        "mode": mode,
        "stub": mode == "stub",
        "model": model,
        "started_at": started_at,
        "wall_seconds_including_startup": wall_seconds,
        "exit_code": result.returncode,
        "json_output_written": json_out.exists(),
        "diff_chars": meta["diff_chars"],
        "usage": usage,
        "run_details_footer": run_details,
        "computed_cost": computed_cost(model, usage),
        "findings": len(((review.get("review") or {}).get("key_issues_to_review")) or []),
        "github_env_removed": removed,
        "command": [part if not part.startswith("--plain_diff.description=") else "--plain_diff.description=<PR body>"
                    for part in command],
    }
    if mode == "stub":
        record["note"] = ("Rehearsal only. The review text and the usage numbers come from scripts/stub_llm.py, "
                          "not from a model. Latency excludes any model time.")
    (run_dir / "record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def summarize_captured_prompts(capture_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(capture_dir.glob("request_*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))["body"]
        messages = body.get("messages", [])
        chars = {m.get("role"): len(m["content"]) if isinstance(m.get("content"), str) else None for m in messages}
        rows.append({
            "file": path.name,
            "model_requested": body.get("model"),
            "system_chars": chars.get("system"),
            "user_chars": chars.get("user"),
            "request_params": sorted(k for k in body if k != "messages"),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["stub", "live"], required=True)
    parser.add_argument("--model", default=None, help="LiteLLM model id for live mode")
    parser.add_argument("--out", required=True, help="Output directory, relative to the lab root")
    parser.add_argument("--pr", action="append", help="PR URL; repeat to override the default three")
    args = parser.parse_args()

    if args.mode == "live" and not args.model:
        parser.error("--model is required in live mode")
    model = "openai/lab-stub" if args.mode == "stub" else args.model
    out_dir = (LAB / args.out).resolve()
    inputs_dir = LAB / "runs" / "step1-inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    stub, stub_port, capture_dir = None, None, out_dir / "captured_requests"
    if args.mode == "stub":
        stub_port = free_port()
        for old in capture_dir.glob("request_*.json") if capture_dir.exists() else []:
            old.unlink()
        stub = subprocess.Popen([sys.executable, "-I", str(LAB / "scripts" / "stub_llm.py"), str(stub_port),
                                 str(capture_dir)])
        time.sleep(1.0)
    try:
        records = []
        for pr_url in args.pr or DEFAULT_PRS:
            meta = fetch_pr(pr_url, inputs_dir)
            record = run_one(meta, args.mode, model, out_dir, stub_port)
            records.append(record)
            print(f"{meta['slug']}: exit={record['exit_code']} wall={record['wall_seconds_including_startup']}s "
                  f"usage={record['usage']} findings={record['findings']}")
    finally:
        if stub:
            stub.terminate()
            stub.wait(timeout=10)

    summary = {"mode": args.mode, "model": model, "versions": versions(), "runs": records}
    if args.mode == "stub":
        summary["captured_prompts"] = summarize_captured_prompts(capture_dir)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"summary: {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()

"""Run with: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import step1_run  # noqa: E402


class ParseRunDetails(unittest.TestCase):
    def test_reads_model_time_and_cost(self):
        markdown = (
            "review text\n<details> <summary><strong>Agent run details</strong></summary>\n\n"
            "- Model: anthropic/claude-sonnet-5-5\n- Tokens: 4,785 in / 100 out / 4,885 total\n"
            "- Prompt cache: 1,700 read\n- Time cost: 12.4s\n- AI calls: 1\n- Estimated API cost: $0.0123 USD\n"
        )
        details = step1_run.parse_run_details(markdown)
        self.assertEqual(details["Model"], "anthropic/claude-sonnet-5-5")
        self.assertEqual(details["model_seconds"], 12.4)
        self.assertEqual(details["cost_usd"], 0.0123)
        self.assertEqual(details["Prompt cache"], "1,700 read")

    def test_unpriced_run_has_no_cost(self):
        details = step1_run.parse_run_details(
            "Agent run details\n- Estimated API cost: unavailable (no calls could be priced)\n")
        self.assertNotIn("cost_usd", details)

    def test_missing_footer_is_empty(self):
        self.assertEqual(step1_run.parse_run_details("no footer here"), {})


class ComputedCost(unittest.TestCase):
    def test_prices_a_known_model_from_tokens(self):
        usage = {"prompt_tokens": 10_000, "completion_tokens": 2_000}
        result = step1_run.computed_cost("anthropic/claude-sonnet-5-5", usage)
        self.assertAlmostEqual(result["cost_usd"], 10_000 * 2e-06 + 2_000 * 1e-05)

    def test_unknown_model_is_not_priced(self):
        result = step1_run.computed_cost("openai/lab-stub", {"prompt_tokens": 100, "completion_tokens": 10})
        self.assertIsNone(result["cost_usd"])


class ChildEnvironment(unittest.TestCase):
    def test_github_credentials_never_reach_pr_agent(self):
        import os
        os.environ["GITHUB_TOKEN"] = "would-be-token"
        os.environ["GH_TOKEN"] = "would-be-token"
        try:
            env, removed = step1_run.child_env("stub", "openai/lab-stub", 1234)
        finally:
            del os.environ["GITHUB_TOKEN"], os.environ["GH_TOKEN"]
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("GH_TOKEN", env)
        self.assertEqual(sorted(removed), ["GH_TOKEN", "GITHUB_TOKEN"])
        self.assertEqual(env["CONFIG__FALLBACK_MODELS"], "[]")

    def test_live_mode_refuses_to_start_without_a_key(self):
        import os
        saved = {k: os.environ.pop(k) for k in list(step1_run.PROVIDER_KEYS) if k in os.environ}
        try:
            with self.assertRaises(SystemExit):
                step1_run.child_env("live", "anthropic/claude-sonnet-5-5", None)
        finally:
            os.environ.update(saved)


class FetchPr(unittest.TestCase):
    def test_rejects_non_pr_urls(self):
        with self.assertRaises(ValueError):
            step1_run.fetch_pr("https://example.com/owner/repo/pull/1", Path("."))


if __name__ == "__main__":
    unittest.main()

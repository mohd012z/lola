import unittest

from lola_full_chain_smoke import run_full_chain_smoke


class FullChainSmokeTests(unittest.TestCase):
    def _names(self):
        return {c["name"] for c in run_full_chain_smoke()["checks"]}

    def test_all_required_checks_present_and_green(self):
        result = run_full_chain_smoke()
        self.assertTrue(result["passed"],
                        f"failed: {[c for c in result['checks'] if not c['ok']]}")
        for required in (
            "happy_path_sovereign_answer",
            "default_deny_before_cognition",
            "novelty_before_external_fuse_pass",
            "unfrozen_external_fuse_cut",
            "prediction_error_feedback_edge",
            "five_key_provenance_contract",
            "chain_deterministic",
        ):
            self.assertIn(required, self._names())
        self.assertTrue(all(c["ok"] for c in result["checks"]))

    def test_chain_records_the_stages(self):
        result = run_full_chain_smoke()
        # the smoke must name the stages it traversed, in order
        stages = result["chain"]
        for s in ("normalize", "gate", "loop", "fuse"):
            self.assertIn(s, stages)
        self.assertLess(stages.index("gate"), stages.index("loop"))

    def test_denial_reports_no_cognition(self):
        # the core Law-2 assertion, reachable directly off the smoke
        from lola_full_chain_smoke import _assert_no_cognition
        out = _assert_no_cognition()
        self.assertTrue(out["ok"], out)


class FullChainCliTest(unittest.TestCase):
    def test_cli_flag_runs_and_passes(self):
        import json
        import subprocess
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [sys.executable, "lola.py", "--full-chain-smoke"],
            capture_output=True, text=True, cwd=repo_root,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["passed"])
        self.assertEqual(len(payload["checks"]), 7)


if __name__ == "__main__":
    unittest.main()

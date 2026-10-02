import subprocess
import tempfile
import unittest
from pathlib import Path

from lola_prospective_result import (
    ANCHOR_SHA,
    PREREGISTRATION_SEAL,
    evaluate_prospective_result,
    verify_commit_order,
)


class ProspectiveResultGateTests(unittest.TestCase):
    def _valid_payload(self):
        return {
            "schema_version": "prospective-transfer-result-v1",
            "registration_id": "lola-preflight-validity-prospective-001",
            "phase": "RESULT",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "selection": {
                "first_eligible_confirmed": True,
                "naturally_occurring": True,
                "benchmark_authored": False,
                "intentionally_injected": False,
                "documentation_only": False,
                "test_only_fixture": False,
                "same_origin_training": False,
                "known_outcome_at_selection": False,
                "cherry_picked": False,
            },
            "chronology": {
                "failure_commit_sha": "1" * 40,
                "selection_lock_commit_sha": "2" * 40,
                "fix_commit_sha": "3" * 40,
                "result_commit_sha": "4" * 40,
                "git_ancestry_verified": True,
            },
            "baseline": {
                "task_id": "prospective-baseline",
                "family": "historical-preflight-validity",
                "transfer_distance": 0,
                "model_id": "kernel-historical-inspector-v2",
                "hardware_id": "frozen-fixture-runtime",
                "verified": True,
                "false_solved": False,
                "intellectual_level": 4,
                "actions": 4,
                "escalations": 0,
                "external_ai_used": False,
                "regression_failures": 0,
            },
            "learned": {
                "task_id": "prospective-holdout",
                "family": "historical-preflight-validity",
                "transfer_distance": 3,
                "model_id": "kernel-historical-inspector-v2",
                "hardware_id": "frozen-fixture-runtime",
                "verified": True,
                "false_solved": False,
                "intellectual_level": 1,
                "actions": 1,
                "escalations": 0,
                "external_ai_used": False,
                "regression_failures": 0,
            },
        }

    def test_valid_governed_result_can_pass_only_with_verified_chronology(self):
        result = evaluate_prospective_result(self._valid_payload(), trust_ancestry_flag=True)
        self.assertTrue(result["valid_contract"])
        self.assertTrue(result["prospective_claim"])
        self.assertTrue(result["blind_holdout_claim"])
        self.assertFalse(result["production_world_claim"])
        self.assertEqual(result["status"], "PROSPECTIVE_TRANSFER_PASS")

    def test_wrong_preregistration_anchor_or_seal_fails_closed(self):
        payload = self._valid_payload()
        payload["preregistration_anchor_sha"] = "a" * 40
        payload["preregistration_seal_sha256"] = "b" * 64
        result = evaluate_prospective_result(payload, trust_ancestry_flag=True)
        self.assertFalse(result["valid_contract"])
        self.assertFalse(result["prospective_claim"])
        self.assertIn("preregistration_anchor_mismatch", result["reasons"])
        self.assertIn("preregistration_seal_mismatch", result["reasons"])

    def test_cherry_pick_or_known_outcome_selection_fails_closed(self):
        payload = self._valid_payload()
        payload["selection"]["cherry_picked"] = True
        payload["selection"]["known_outcome_at_selection"] = True
        result = evaluate_prospective_result(payload, trust_ancestry_flag=True)
        self.assertFalse(result["prospective_claim"])
        self.assertIn("cherry_pick_forbidden", result["reasons"])
        self.assertIn("outcome_known_at_selection", result["reasons"])

    def test_growth_failure_is_valid_evidence_but_not_a_pass(self):
        payload = self._valid_payload()
        payload["learned"]["actions"] = 5
        payload["learned"]["intellectual_level"] = 4
        result = evaluate_prospective_result(payload, trust_ancestry_flag=True)
        self.assertTrue(result["valid_contract"])
        self.assertFalse(result["prospective_claim"])
        self.assertEqual(result["status"], "PROSPECTIVE_TRANSFER_FAIL")
        self.assertIn("no_intellectual_downshift", result["growth_reasons"])
        self.assertIn("actions_increased", result["growth_reasons"])

    def test_git_ancestry_requires_anchor_failure_selection_fix_result_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "LOLA Test"], check=True)

            shas = []
            for index, label in enumerate(("anchor", "failure", "selection", "fix", "result")):
                (repo / "state.txt").write_text(f"{index}:{label}\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(repo), "add", "state.txt"], check=True)
                subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", label], check=True)
                sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
                shas.append(sha)

            self.assertTrue(verify_commit_order(repo, *shas))
            self.assertFalse(verify_commit_order(repo, shas[0], shas[2], shas[1], shas[3], shas[4]))


if __name__ == "__main__":
    unittest.main()

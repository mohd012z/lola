import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from lola import main
from lola_prospective_result import (
    ANCHOR_SHA,
    PREREGISTRATION_SEAL,
    evaluate_prospective_result,
    verify_commit_order,
)


def _digest(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ProspectiveResultGateTests(unittest.TestCase):
    def _valid_payload(self):
        selection = {
            "first_eligible_confirmed": True,
            "naturally_occurring": True,
            "benchmark_authored": False,
            "intentionally_injected": False,
            "documentation_only": False,
            "test_only_fixture": False,
            "same_origin_training": False,
            "known_outcome_at_selection": False,
            "cherry_picked": False,
            "surface": "workflow",
            "before_evidence_refs": ["ci:run-123"],
            "prior_post_anchor_failures_reviewed": [],
        }
        selection_lock = {
            "schema_version": "prospective-holdout-selection-lock-v1",
            "registration_id": "lola-preflight-validity-prospective-001",
            "phase": "SELECTION_LOCK",
            "status": "LOCKED_AWAITING_REPAIR",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "failure_commit_sha": "1" * 40,
            "candidate_digest_sha256": "a" * 64,
            "observation_digest_sha256": "b" * 64,
            "eligibility_review_digest_sha256": "c" * 64,
            "eligibility_reviewer_id": "reviewer-independent",
            "selection": dict(selection),
            "outcome_at_selection": "UNKNOWN",
            "fix_commit_sha": None,
            "result_commit_sha": None,
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
        }
        selection_lock["selection_lock_digest_sha256"] = _digest(selection_lock)
        repair_authorization = {
            "schema_version": "prospective-repair-authorization-v1",
            "registration_id": "lola-preflight-validity-prospective-001",
            "phase": "REPAIR_AUTHORIZATION",
            "status": "AUTHORIZED_AWAITING_REPAIR",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "failure_commit_sha": "1" * 40,
            "selection_lock_commit_sha": "2" * 40,
            "selection_lock_digest_sha256": selection_lock["selection_lock_digest_sha256"],
            "authorizer_id": "repair-authorizer-explicit",
            "authorization_mode": "AUTOMATED_REPAIR",
            "authorization_reason": "Repair the independently selected prospective holdout.",
            "repair_authorized": True,
            "automated_repair_authorized": True,
            "repair_outcome": "UNKNOWN",
            "fix_commit_sha": None,
            "result_commit_sha": None,
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
        }
        repair_authorization["repair_authorization_digest_sha256"] = _digest(
            repair_authorization
        )
        baseline = {
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
        }
        learned = {
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
        }
        result_evidence = {
            "schema_version": "prospective-result-evidence-v1",
            "registration_id": "lola-preflight-validity-prospective-001",
            "phase": "RESULT_EVIDENCE",
            "status": "VERIFIED_RESULT_EVIDENCE",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "selection_lock_digest_sha256": selection_lock["selection_lock_digest_sha256"],
            "repair_authorization_digest_sha256": repair_authorization[
                "repair_authorization_digest_sha256"
            ],
            "failure_commit_sha": "1" * 40,
            "selection_lock_commit_sha": "2" * 40,
            "repair_authorization_commit_sha": "3" * 40,
            "fix_commit_sha": "4" * 40,
            "repair_outcome": "VERIFIED",
            "after_evidence_refs": ["ci:after-run-456"],
            "baseline": baseline,
            "learned": learned,
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
        }
        result_evidence["result_evidence_digest_sha256"] = _digest(result_evidence)
        return {
            "schema_version": "prospective-transfer-result-v1",
            "registration_id": "lola-preflight-validity-prospective-001",
            "phase": "RESULT",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "selection": selection,
            "selection_lock_path": "evidence/prospective-selection-lock.json",
            "selection_lock_artifact": selection_lock,
            "repair_authorization_path": "evidence/prospective-repair-authorization.json",
            "repair_authorization_artifact": repair_authorization,
            "result_evidence_path": "evidence/prospective-result-evidence.json",
            "result_evidence_artifact": result_evidence,
            "chronology": {
                "failure_commit_sha": "1" * 40,
                "selection_lock_commit_sha": "2" * 40,
                "repair_authorization_commit_sha": "3" * 40,
                "fix_commit_sha": "4" * 40,
                "result_commit_sha": "5" * 40,
                "git_ancestry_verified": True,
            },
            "baseline": baseline,
            "learned": learned,
        }

    def _refresh_result_evidence_digest(self, payload):
        evidence = payload["result_evidence_artifact"]
        evidence.pop("result_evidence_digest_sha256", None)
        evidence["result_evidence_digest_sha256"] = _digest(evidence)

    def test_valid_governed_result_can_pass_only_with_verified_chronology(self):
        result = evaluate_prospective_result(self._valid_payload(), trust_ancestry_flag=True)
        self.assertTrue(result["valid_contract"])
        self.assertTrue(result["prospective_claim"])
        self.assertTrue(result["blind_holdout_claim"])
        self.assertTrue(result["selection_lock_verified"])
        self.assertTrue(result["repair_authorization_verified"])
        self.assertTrue(result["result_evidence_verified"])
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
        payload["result_evidence_artifact"]["learned"] = payload["learned"]
        self._refresh_result_evidence_digest(payload)
        result = evaluate_prospective_result(payload, trust_ancestry_flag=True)
        self.assertTrue(result["valid_contract"])
        self.assertFalse(result["prospective_claim"])
        self.assertEqual(result["status"], "PROSPECTIVE_TRANSFER_FAIL")
        self.assertIn("no_intellectual_downshift", result["growth_reasons"])
        self.assertIn("actions_increased", result["growth_reasons"])

    def test_git_ancestry_requires_authorization_before_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "LOLA Test"], check=True)

            shas = []
            for index, label in enumerate(
                ("anchor", "failure", "selection", "authorization", "fix", "result")
            ):
                (repo / "state.txt").write_text(f"{index}:{label}\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(repo), "add", "state.txt"], check=True)
                subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", label], check=True)
                sha = subprocess.check_output(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
                ).strip()
                shas.append(sha)

            self.assertTrue(verify_commit_order(repo, *shas))
            self.assertFalse(
                verify_commit_order(
                    repo,
                    shas[0],
                    shas[1],
                    shas[2],
                    shas[4],
                    shas[3],
                    shas[5],
                )
            )

    def test_cli_uses_real_git_ancestry_and_rejects_synthetic_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            path.write_text(json.dumps(self._valid_payload()), encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(sys, "argv", ["lola.py", "--prospective-transfer-result", str(path)]):
                with redirect_stdout(stdout):
                    rc = main()

        self.assertEqual(rc, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["prospective_claim"])
        self.assertFalse(payload["git_ancestry_verified"])
        self.assertIn("git_ancestry_not_verified", payload["reasons"])


if __name__ == "__main__":
    unittest.main()

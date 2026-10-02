import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lola_prospective_result import (
    ANCHOR_SHA,
    PREREGISTRATION_SEAL,
    REGISTRATION_ID,
    evaluate_prospective_result,
)


def _digest(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ProspectiveResultSelectionLockBindingTests(unittest.TestCase):
    def _selection(self):
        return {
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

    def _lock(self, failure_sha="1" * 40, *, anchor_sha=ANCHOR_SHA):
        lock = {
            "schema_version": "prospective-holdout-selection-lock-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "SELECTION_LOCK",
            "status": "LOCKED_AWAITING_REPAIR",
            "preregistration_anchor_sha": anchor_sha,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "failure_commit_sha": failure_sha,
            "candidate_digest_sha256": "a" * 64,
            "observation_digest_sha256": "b" * 64,
            "eligibility_review_digest_sha256": "c" * 64,
            "eligibility_reviewer_id": "reviewer-independent",
            "selection": self._selection(),
            "outcome_at_selection": "UNKNOWN",
            "fix_commit_sha": None,
            "result_commit_sha": None,
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
        }
        lock["selection_lock_digest_sha256"] = _digest(lock)
        return lock

    def _payload(self):
        lock = self._lock()
        return {
            "schema_version": "prospective-transfer-result-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "RESULT",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "selection": dict(lock["selection"]),
            "selection_lock_path": "evidence/prospective-selection-lock.json",
            "selection_lock_artifact": lock,
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

    def test_missing_selection_lock_binding_is_invalid(self):
        payload = self._payload()
        payload.pop("selection_lock_path")
        payload.pop("selection_lock_artifact")

        result = evaluate_prospective_result(payload, trust_ancestry_flag=True)

        self.assertFalse(result["valid_contract"])
        self.assertFalse(result["prospective_claim"])
        self.assertIn("selection_lock_binding_missing", result["reasons"])

    def test_tampered_selection_lock_digest_is_invalid(self):
        payload = self._payload()
        payload["selection_lock_artifact"]["selection"]["surface"] = "source"

        result = evaluate_prospective_result(payload, trust_ancestry_flag=True)

        self.assertFalse(result["valid_contract"])
        self.assertFalse(result["prospective_claim"])
        self.assertIn("selection_lock_digest_mismatch", result["reasons"])

    def test_result_selection_must_match_authenticated_lock(self):
        payload = self._payload()
        payload["selection"]["surface"] = "source"

        result = evaluate_prospective_result(payload, trust_ancestry_flag=True)

        self.assertFalse(result["valid_contract"])
        self.assertIn("selection_lock_selection_mismatch", result["reasons"])

    def test_valid_authenticated_lock_can_pass_isolated_governance(self):
        result = evaluate_prospective_result(self._payload(), trust_ancestry_flag=True)

        self.assertTrue(result["valid_contract"])
        self.assertTrue(result["prospective_claim"])
        self.assertTrue(result["selection_lock_verified"])

    def test_production_missing_lock_at_selection_commit_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "LOLA Test"], check=True)

            def commit(label):
                (repo / "state.txt").write_text(label, encoding="utf-8")
                subprocess.run(["git", "-C", str(repo), "add", "state.txt"], check=True)
                subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", label], check=True)
                return subprocess.check_output(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
                ).strip()

            anchor = commit("anchor")
            failure = commit("failure")
            selection_commit = commit("selection-without-lock")
            fix = commit("fix")
            result_commit = commit("result")

            payload = self._payload()
            payload["preregistration_anchor_sha"] = anchor
            payload["selection_lock_artifact"] = self._lock(failure, anchor_sha=anchor)
            payload["chronology"] = {
                "failure_commit_sha": failure,
                "selection_lock_commit_sha": selection_commit,
                "fix_commit_sha": fix,
                "result_commit_sha": result_commit,
                "git_ancestry_verified": True,
            }

            with patch("lola_prospective_result.ANCHOR_SHA", anchor):
                outcome = evaluate_prospective_result(payload, repository_root=repo)

        self.assertFalse(outcome["valid_contract"])
        self.assertFalse(outcome["prospective_claim"])
        self.assertIn("selection_lock_artifact_not_found_at_selection_commit", outcome["reasons"])

    def test_production_uses_committed_lock_not_embedded_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "LOLA Test"], check=True)

            def commit(label, extra_path=None, extra_payload=None):
                (repo / "state.txt").write_text(label, encoding="utf-8")
                if extra_path is not None:
                    path = repo / extra_path
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps(extra_payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
                subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", label], check=True)
                return subprocess.check_output(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
                ).strip()

            anchor = commit("anchor")
            failure = commit("failure")
            valid_lock = self._lock(failure, anchor_sha=anchor)
            tampered_lock = json.loads(json.dumps(valid_lock))
            tampered_lock["selection"]["surface"] = "source"
            selection_commit = commit(
                "selection-with-tampered-lock",
                "evidence/prospective-selection-lock.json",
                tampered_lock,
            )
            fix = commit("fix")
            result_commit = commit("result")

            payload = self._payload()
            payload["preregistration_anchor_sha"] = anchor
            payload["selection_lock_artifact"] = valid_lock
            payload["chronology"] = {
                "failure_commit_sha": failure,
                "selection_lock_commit_sha": selection_commit,
                "fix_commit_sha": fix,
                "result_commit_sha": result_commit,
                "git_ancestry_verified": True,
            }

            with patch("lola_prospective_result.ANCHOR_SHA", anchor):
                outcome = evaluate_prospective_result(payload, repository_root=repo)

        self.assertFalse(outcome["valid_contract"])
        self.assertFalse(outcome["prospective_claim"])
        self.assertIn("selection_lock_digest_mismatch", outcome["reasons"])


if __name__ == "__main__":
    unittest.main()

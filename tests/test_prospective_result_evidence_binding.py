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


class ProspectiveResultEvidenceBindingTests(unittest.TestCase):
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
            "before_evidence_refs": ["ci:before-run-123"],
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

    def _baseline(self):
        return {
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

    def _learned(self):
        return {
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

    def _result_evidence(
        self,
        *,
        anchor_sha=ANCHOR_SHA,
        failure_sha="1" * 40,
        selection_sha="2" * 40,
        fix_sha="3" * 40,
        selection_lock_digest="d" * 64,
    ):
        evidence = {
            "schema_version": "prospective-result-evidence-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "RESULT_EVIDENCE",
            "status": "VERIFIED_RESULT_EVIDENCE",
            "preregistration_anchor_sha": anchor_sha,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "selection_lock_digest_sha256": selection_lock_digest,
            "failure_commit_sha": failure_sha,
            "selection_lock_commit_sha": selection_sha,
            "fix_commit_sha": fix_sha,
            "repair_outcome": "VERIFIED",
            "after_evidence_refs": ["ci:after-run-456"],
            "baseline": self._baseline(),
            "learned": self._learned(),
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
        }
        evidence["result_evidence_digest_sha256"] = _digest(evidence)
        return evidence

    def _payload(self):
        lock = self._lock()
        evidence = self._result_evidence(
            selection_lock_digest=lock["selection_lock_digest_sha256"]
        )
        return {
            "schema_version": "prospective-transfer-result-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "RESULT",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "selection": self._selection(),
            "selection_lock_path": "evidence/prospective-selection-lock.json",
            "selection_lock_artifact": lock,
            "result_evidence_path": "evidence/prospective-result-evidence.json",
            "result_evidence_artifact": evidence,
            "chronology": {
                "failure_commit_sha": "1" * 40,
                "selection_lock_commit_sha": "2" * 40,
                "fix_commit_sha": "3" * 40,
                "result_commit_sha": "4" * 40,
                "git_ancestry_verified": True,
            },
            "baseline": self._baseline(),
            "learned": self._learned(),
        }

    def test_missing_result_evidence_binding_is_invalid(self):
        payload = self._payload()
        payload.pop("result_evidence_path")
        payload.pop("result_evidence_artifact")

        result = evaluate_prospective_result(payload, trust_ancestry_flag=True)

        self.assertFalse(result["valid_contract"])
        self.assertFalse(result["prospective_claim"])
        self.assertIn("result_evidence_binding_missing", result["reasons"])

    def test_tampered_result_evidence_digest_is_invalid(self):
        payload = self._payload()
        payload["result_evidence_artifact"]["learned"]["actions"] = 2

        result = evaluate_prospective_result(payload, trust_ancestry_flag=True)

        self.assertFalse(result["valid_contract"])
        self.assertFalse(result["prospective_claim"])
        self.assertIn("result_evidence_digest_mismatch", result["reasons"])

    def test_result_trials_must_match_authenticated_evidence(self):
        payload = self._payload()
        payload["learned"]["actions"] = 2

        result = evaluate_prospective_result(payload, trust_ancestry_flag=True)

        self.assertFalse(result["valid_contract"])
        self.assertIn("result_evidence_trials_mismatch", result["reasons"])

    def test_valid_authenticated_result_evidence_can_pass_isolated_governance(self):
        result = evaluate_prospective_result(self._payload(), trust_ancestry_flag=True)

        self.assertTrue(result["valid_contract"])
        self.assertTrue(result["prospective_claim"])
        self.assertTrue(result["result_evidence_verified"])
        self.assertEqual(
            result["result_evidence_digest_sha256"],
            self._payload()["result_evidence_artifact"]["result_evidence_digest_sha256"],
        )

    def _init_repo_chain(self, *, committed_evidence=None):
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "LOLA Test"], check=True)

        def commit(label, files=None):
            (repo / "state.txt").write_text(label, encoding="utf-8")
            if files:
                for relpath, content in files.items():
                    path = repo / relpath
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(content, sort_keys=True), encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", label], check=True)
            return subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip()

        anchor = commit("anchor")
        failure = commit("failure")
        lock = self._lock(failure, anchor_sha=anchor)
        selection = commit(
            "selection",
            {"evidence/prospective-selection-lock.json": lock},
        )
        fix = commit("fix")

        if committed_evidence == "valid":
            evidence = self._result_evidence(
                anchor_sha=anchor,
                failure_sha=failure,
                selection_sha=selection,
                fix_sha=fix,
                selection_lock_digest=lock["selection_lock_digest_sha256"],
            )
            result_commit = commit(
                "result",
                {"evidence/prospective-result-evidence.json": evidence},
            )
        elif committed_evidence == "tampered":
            evidence = self._result_evidence(
                anchor_sha=anchor,
                failure_sha=failure,
                selection_sha=selection,
                fix_sha=fix,
                selection_lock_digest=lock["selection_lock_digest_sha256"],
            )
            evidence["learned"]["actions"] = 2
            result_commit = commit(
                "result",
                {"evidence/prospective-result-evidence.json": evidence},
            )
        else:
            evidence = None
            result_commit = commit("result")

        return tmp, repo, anchor, failure, selection, fix, result_commit, lock, evidence

    def _production_payload(self, anchor, failure, selection, fix, result_commit, lock):
        payload = self._payload()
        payload["preregistration_anchor_sha"] = anchor
        payload["selection_lock_artifact"] = lock
        payload["result_evidence_artifact"] = self._result_evidence(
            anchor_sha=anchor,
            failure_sha=failure,
            selection_sha=selection,
            fix_sha=fix,
            selection_lock_digest=lock["selection_lock_digest_sha256"],
        )
        payload["chronology"] = {
            "failure_commit_sha": failure,
            "selection_lock_commit_sha": selection,
            "fix_commit_sha": fix,
            "result_commit_sha": result_commit,
            "git_ancestry_verified": True,
        }
        return payload

    def test_production_missing_result_evidence_at_result_commit_is_invalid(self):
        tmp, repo, anchor, failure, selection, fix, result_commit, lock, _ = self._init_repo_chain()
        try:
            payload = self._production_payload(anchor, failure, selection, fix, result_commit, lock)
            with patch("lola_prospective_result.ANCHOR_SHA", anchor):
                outcome = evaluate_prospective_result(payload, repository_root=repo)
        finally:
            tmp.cleanup()

        self.assertFalse(outcome["valid_contract"])
        self.assertFalse(outcome["prospective_claim"])
        self.assertIn("result_evidence_artifact_not_found_at_result_commit", outcome["reasons"])

    def test_production_uses_committed_result_evidence_not_embedded_copy(self):
        tmp, repo, anchor, failure, selection, fix, result_commit, lock, _ = self._init_repo_chain(
            committed_evidence="tampered"
        )
        try:
            payload = self._production_payload(anchor, failure, selection, fix, result_commit, lock)
            with patch("lola_prospective_result.ANCHOR_SHA", anchor):
                outcome = evaluate_prospective_result(payload, repository_root=repo)
        finally:
            tmp.cleanup()

        self.assertFalse(outcome["valid_contract"])
        self.assertFalse(outcome["prospective_claim"])
        self.assertIn("result_evidence_digest_mismatch", outcome["reasons"])


if __name__ == "__main__":
    unittest.main()

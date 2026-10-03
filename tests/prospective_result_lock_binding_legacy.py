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

    def _authorization(
        self,
        lock,
        *,
        anchor_sha=ANCHOR_SHA,
        failure_sha="1" * 40,
        selection_sha="2" * 40,
    ):
        authorization = {
            "schema_version": "prospective-repair-authorization-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "REPAIR_AUTHORIZATION",
            "status": "AUTHORIZED_AWAITING_REPAIR",
            "preregistration_anchor_sha": anchor_sha,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "failure_commit_sha": failure_sha,
            "selection_lock_commit_sha": selection_sha,
            "selection_lock_digest_sha256": lock["selection_lock_digest_sha256"],
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
        authorization["repair_authorization_digest_sha256"] = _digest(authorization)
        return authorization

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
        lock,
        authorization,
        *,
        anchor_sha=ANCHOR_SHA,
        failure_sha="1" * 40,
        selection_sha="2" * 40,
        authorization_sha="3" * 40,
        fix_sha="4" * 40,
    ):
        evidence = {
            "schema_version": "prospective-result-evidence-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "RESULT_EVIDENCE",
            "status": "VERIFIED_RESULT_EVIDENCE",
            "preregistration_anchor_sha": anchor_sha,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "selection_lock_digest_sha256": lock["selection_lock_digest_sha256"],
            "repair_authorization_digest_sha256": authorization[
                "repair_authorization_digest_sha256"
            ],
            "failure_commit_sha": failure_sha,
            "selection_lock_commit_sha": selection_sha,
            "repair_authorization_commit_sha": authorization_sha,
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
        authorization = self._authorization(lock)
        baseline = self._baseline()
        learned = self._learned()
        return {
            "schema_version": "prospective-transfer-result-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "RESULT",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "selection": dict(lock["selection"]),
            "selection_lock_path": "evidence/prospective-selection-lock.json",
            "selection_lock_artifact": lock,
            "repair_authorization_path": "evidence/prospective-repair-authorization.json",
            "repair_authorization_artifact": authorization,
            "result_evidence_path": "evidence/prospective-result-evidence.json",
            "result_evidence_artifact": self._result_evidence(lock, authorization),
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
        self.assertTrue(result["repair_authorization_verified"])
        self.assertTrue(result["result_evidence_verified"])

    def _init_repo(self):
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "LOLA Test"], check=True)
        return tmp, repo

    def _commit(self, repo, label, files=None):
        (repo / "state.txt").write_text(label, encoding="utf-8")
        if files:
            for relpath, content in files.items():
                path = repo / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(content, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", label], check=True)
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()

    def _finish_chain(self, repo, anchor, failure, selection_commit, valid_lock):
        authorization = self._authorization(
            valid_lock,
            anchor_sha=anchor,
            failure_sha=failure,
            selection_sha=selection_commit,
        )
        authorization_commit = self._commit(
            repo,
            "authorization",
            {"evidence/prospective-repair-authorization.json": authorization},
        )
        fix = self._commit(repo, "fix")
        evidence = self._result_evidence(
            valid_lock,
            authorization,
            anchor_sha=anchor,
            failure_sha=failure,
            selection_sha=selection_commit,
            authorization_sha=authorization_commit,
            fix_sha=fix,
        )
        result_commit = self._commit(
            repo,
            "result",
            {"evidence/prospective-result-evidence.json": evidence},
        )
        return authorization, authorization_commit, fix, result_commit, evidence

    def _production_payload(
        self,
        anchor,
        failure,
        selection_commit,
        authorization_commit,
        fix,
        result_commit,
        valid_lock,
        authorization,
        evidence,
    ):
        payload = self._payload()
        payload["preregistration_anchor_sha"] = anchor
        payload["selection_lock_artifact"] = valid_lock
        payload["repair_authorization_artifact"] = authorization
        payload["result_evidence_artifact"] = evidence
        payload["chronology"] = {
            "failure_commit_sha": failure,
            "selection_lock_commit_sha": selection_commit,
            "repair_authorization_commit_sha": authorization_commit,
            "fix_commit_sha": fix,
            "result_commit_sha": result_commit,
            "git_ancestry_verified": True,
        }
        return payload

    def test_production_missing_lock_at_selection_commit_is_invalid(self):
        tmp, repo = self._init_repo()
        try:
            anchor = self._commit(repo, "anchor")
            failure = self._commit(repo, "failure")
            valid_lock = self._lock(failure, anchor_sha=anchor)
            selection_commit = self._commit(repo, "selection-without-lock")
            authorization, authorization_commit, fix, result_commit, evidence = self._finish_chain(
                repo, anchor, failure, selection_commit, valid_lock
            )
            payload = self._production_payload(
                anchor,
                failure,
                selection_commit,
                authorization_commit,
                fix,
                result_commit,
                valid_lock,
                authorization,
                evidence,
            )

            with patch("lola_prospective_result.ANCHOR_SHA", anchor):
                outcome = evaluate_prospective_result(payload, repository_root=repo)
        finally:
            tmp.cleanup()

        self.assertFalse(outcome["valid_contract"])
        self.assertFalse(outcome["prospective_claim"])
        self.assertIn("selection_lock_artifact_not_found_at_selection_commit", outcome["reasons"])

    def test_production_uses_committed_lock_not_embedded_copy(self):
        tmp, repo = self._init_repo()
        try:
            anchor = self._commit(repo, "anchor")
            failure = self._commit(repo, "failure")
            valid_lock = self._lock(failure, anchor_sha=anchor)
            tampered_lock = json.loads(json.dumps(valid_lock))
            tampered_lock["selection"]["surface"] = "source"
            selection_commit = self._commit(
                repo,
                "selection-with-tampered-lock",
                {"evidence/prospective-selection-lock.json": tampered_lock},
            )
            authorization, authorization_commit, fix, result_commit, evidence = self._finish_chain(
                repo, anchor, failure, selection_commit, valid_lock
            )
            payload = self._production_payload(
                anchor,
                failure,
                selection_commit,
                authorization_commit,
                fix,
                result_commit,
                valid_lock,
                authorization,
                evidence,
            )

            with patch("lola_prospective_result.ANCHOR_SHA", anchor):
                outcome = evaluate_prospective_result(payload, repository_root=repo)
        finally:
            tmp.cleanup()

        self.assertFalse(outcome["valid_contract"])
        self.assertFalse(outcome["prospective_claim"])
        self.assertIn("selection_lock_digest_mismatch", outcome["reasons"])


if __name__ == "__main__":
    unittest.main()

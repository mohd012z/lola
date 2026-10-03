import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lola_prospective_result import ANCHOR_SHA, evaluate_prospective_result
from prospective_repair_authorization_binding_legacy import (
    ProspectiveRepairAuthorizationBindingTests,
    _digest,
)


class ProspectiveExecutionReceiptBindingTests(unittest.TestCase):
    def setUp(self):
        self.helper = ProspectiveRepairAuthorizationBindingTests()

    def _receipt(
        self,
        payload,
        *,
        anchor_sha=ANCHOR_SHA,
        failure_sha="1" * 40,
        selection_sha="2" * 40,
        authorization_sha="3" * 40,
        fix_sha="4" * 40,
        fix_parent_sha="3" * 40,
        fix_tree_sha="6" * 40,
        fix_patch_sha256="7" * 64,
    ):
        authorization = payload["repair_authorization_artifact"]
        receipt = {
            "schema_version": "prospective-repair-execution-receipt-v1",
            "registration_id": payload["registration_id"],
            "phase": "REPAIR_EXECUTION_RECEIPT",
            "status": "EXECUTED_AWAITING_RESULT",
            "preregistration_anchor_sha": anchor_sha,
            "preregistration_seal_sha256": payload["preregistration_seal_sha256"],
            "failure_commit_sha": failure_sha,
            "selection_lock_commit_sha": selection_sha,
            "selection_lock_digest_sha256": payload["selection_lock_artifact"][
                "selection_lock_digest_sha256"
            ],
            "repair_authorization_commit_sha": authorization_sha,
            "repair_authorization_digest_sha256": authorization[
                "repair_authorization_digest_sha256"
            ],
            "authorized_executor_id": authorization["authorized_executor_id"],
            "execution_nonce_sha256": authorization["execution_nonce_sha256"],
            "authorization_consumed": True,
            "fix_commit_sha": fix_sha,
            "fix_parent_sha": fix_parent_sha,
            "fix_tree_sha": fix_tree_sha,
            "fix_patch_sha256": fix_patch_sha256,
            "repair_outcome": "UNKNOWN",
            "result_commit_sha": None,
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
        }
        receipt["repair_execution_receipt_digest_sha256"] = _digest(receipt)
        return receipt

    def _payload_with_receipt(self):
        payload = self.helper._payload()
        authorization = payload["repair_authorization_artifact"]
        authorization["authorized_executor_id"] = "lola-repair-executor-v1"
        authorization["execution_nonce_sha256"] = "f" * 64
        authorization["single_use"] = True
        authorization["execution_receipt_path"] = (
            "evidence/prospective-repair-execution-receipt.json"
        )
        authorization.pop("repair_authorization_digest_sha256", None)
        authorization["repair_authorization_digest_sha256"] = _digest(authorization)

        evidence = payload["result_evidence_artifact"]
        evidence["repair_authorization_digest_sha256"] = authorization[
            "repair_authorization_digest_sha256"
        ]

        receipt = self._receipt(payload)
        payload["repair_execution_receipt_path"] = (
            "evidence/prospective-repair-execution-receipt.json"
        )
        payload["repair_execution_receipt_artifact"] = receipt
        payload["chronology"]["repair_execution_receipt_commit_sha"] = "8" * 40
        evidence["repair_execution_receipt_commit_sha"] = "8" * 40
        evidence["repair_execution_receipt_digest_sha256"] = receipt[
            "repair_execution_receipt_digest_sha256"
        ]
        evidence.pop("result_evidence_digest_sha256", None)
        evidence["result_evidence_digest_sha256"] = _digest(evidence)
        return payload

    def test_authorized_fix_without_execution_receipt_is_invalid(self):
        payload = self.helper._payload()
        payload["execution_receipt_contract_required"] = True

        outcome = evaluate_prospective_result(payload, trust_ancestry_flag=True)

        self.assertFalse(outcome["valid_contract"])
        self.assertFalse(outcome["prospective_claim"])
        self.assertIn("repair_execution_receipt_binding_missing", outcome["reasons"])

    def test_tampered_execution_receipt_digest_is_invalid(self):
        payload = self._payload_with_receipt()
        payload["repair_execution_receipt_artifact"]["authorized_executor_id"] = "tampered"

        outcome = evaluate_prospective_result(payload, trust_ancestry_flag=True)

        self.assertFalse(outcome["valid_contract"])
        self.assertIn("repair_execution_receipt_digest_mismatch", outcome["reasons"])

    def test_execution_receipt_must_bind_exact_authorization_and_fix(self):
        payload = self._payload_with_receipt()
        receipt = payload["repair_execution_receipt_artifact"]
        receipt["repair_authorization_digest_sha256"] = "a" * 64
        receipt["fix_commit_sha"] = "9" * 40
        receipt.pop("repair_execution_receipt_digest_sha256", None)
        receipt["repair_execution_receipt_digest_sha256"] = _digest(receipt)

        outcome = evaluate_prospective_result(payload, trust_ancestry_flag=True)

        self.assertFalse(outcome["valid_contract"])
        self.assertIn("repair_execution_receipt_authorization_mismatch", outcome["reasons"])
        self.assertIn("repair_execution_receipt_fix_mismatch", outcome["reasons"])

    def test_execution_receipt_cannot_claim_repair_outcome_or_result(self):
        payload = self._payload_with_receipt()
        receipt = payload["repair_execution_receipt_artifact"]
        receipt["repair_outcome"] = "VERIFIED"
        receipt["result_commit_sha"] = "5" * 40
        receipt.pop("repair_execution_receipt_digest_sha256", None)
        receipt["repair_execution_receipt_digest_sha256"] = _digest(receipt)

        outcome = evaluate_prospective_result(payload, trust_ancestry_flag=True)

        self.assertFalse(outcome["valid_contract"])
        self.assertIn("repair_execution_receipt_outcome_known", outcome["reasons"])
        self.assertIn("repair_execution_receipt_result_already_known", outcome["reasons"])

    def test_valid_execution_receipt_can_pass_isolated_governance(self):
        outcome = evaluate_prospective_result(
            self._payload_with_receipt(), trust_ancestry_flag=True
        )

        self.assertTrue(outcome["valid_contract"])
        self.assertTrue(outcome["repair_execution_receipt_verified"])
        self.assertTrue(outcome["prospective_claim"])

    def _init_production_chain(self, *, committed_receipt="missing"):
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "LOLA Test"],
            check=True,
        )

        def commit(label, files=None):
            (repo / "state.txt").write_text(label, encoding="utf-8")
            for relpath, content in (files or {}).items():
                path = repo / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(content, sort_keys=True), encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-q", "-m", label], check=True
            )
            return subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip()

        anchor = commit("anchor")
        failure = commit("failure")
        lock = self.helper._lock(failure, anchor_sha=anchor)
        selection = commit(
            "selection", {"evidence/prospective-selection-lock.json": lock}
        )
        authorization = self.helper._authorization(
            anchor_sha=anchor,
            failure_sha=failure,
            selection_sha=selection,
            selection_lock_digest=lock["selection_lock_digest_sha256"],
        )
        authorization["authorized_executor_id"] = "lola-repair-executor-v1"
        authorization["execution_nonce_sha256"] = "f" * 64
        authorization["single_use"] = True
        authorization["execution_receipt_path"] = (
            "evidence/prospective-repair-execution-receipt.json"
        )
        authorization.pop("repair_authorization_digest_sha256", None)
        authorization["repair_authorization_digest_sha256"] = _digest(authorization)
        authorization_commit = commit(
            "authorization",
            {"evidence/prospective-repair-authorization.json": authorization},
        )
        fix = commit("fix")
        fix_tree = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", f"{fix}^{{tree}}"], text=True
        ).strip()
        patch_bytes = subprocess.check_output(
            ["git", "-C", str(repo), "diff", "--binary", authorization_commit, fix]
        )
        import hashlib

        fix_patch_digest = hashlib.sha256(patch_bytes).hexdigest()
        payload = self.helper._payload()
        payload["preregistration_anchor_sha"] = anchor
        payload["selection_lock_artifact"] = lock
        payload["repair_authorization_artifact"] = authorization
        payload["repair_execution_receipt_path"] = (
            "evidence/prospective-repair-execution-receipt.json"
        )
        receipt = self._receipt(
            payload,
            anchor_sha=anchor,
            failure_sha=failure,
            selection_sha=selection,
            authorization_sha=authorization_commit,
            fix_sha=fix,
            fix_parent_sha=authorization_commit,
            fix_tree_sha=fix_tree,
            fix_patch_sha256=fix_patch_digest,
        )
        receipt_files = {}
        if committed_receipt == "valid":
            receipt_files["evidence/prospective-repair-execution-receipt.json"] = receipt
        elif committed_receipt == "tampered":
            tampered = json.loads(json.dumps(receipt))
            tampered["authorized_executor_id"] = "tampered-after-digest"
            receipt_files["evidence/prospective-repair-execution-receipt.json"] = tampered
        receipt_commit = commit("execution-receipt", receipt_files)

        result_evidence = self.helper._result_evidence(
            anchor_sha=anchor,
            failure_sha=failure,
            selection_sha=selection,
            authorization_sha=authorization_commit,
            fix_sha=fix,
            selection_lock_digest=lock["selection_lock_digest_sha256"],
            authorization_digest=authorization["repair_authorization_digest_sha256"],
        )
        result_evidence["repair_execution_receipt_commit_sha"] = receipt_commit
        result_evidence["repair_execution_receipt_digest_sha256"] = receipt[
            "repair_execution_receipt_digest_sha256"
        ]
        result_evidence.pop("result_evidence_digest_sha256", None)
        result_evidence["result_evidence_digest_sha256"] = _digest(result_evidence)
        result_commit = commit(
            "result", {"evidence/prospective-result-evidence.json": result_evidence}
        )
        payload["repair_execution_receipt_artifact"] = receipt
        payload["result_evidence_artifact"] = result_evidence
        payload["chronology"] = {
            "failure_commit_sha": failure,
            "selection_lock_commit_sha": selection,
            "repair_authorization_commit_sha": authorization_commit,
            "fix_commit_sha": fix,
            "repair_execution_receipt_commit_sha": receipt_commit,
            "result_commit_sha": result_commit,
            "git_ancestry_verified": True,
        }
        return tmp, repo, anchor, payload

    def test_production_missing_committed_execution_receipt_is_invalid(self):
        tmp, repo, anchor, payload = self._init_production_chain(
            committed_receipt="missing"
        )
        try:
            with patch("lola_prospective_result.ANCHOR_SHA", anchor):
                outcome = evaluate_prospective_result(payload, repository_root=repo)
        finally:
            tmp.cleanup()

        self.assertFalse(outcome["valid_contract"])
        self.assertIn(
            "repair_execution_receipt_artifact_not_found_at_receipt_commit",
            outcome["reasons"],
        )


if __name__ == "__main__":
    unittest.main()

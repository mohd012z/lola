import hashlib
import json
import unittest

from lola_prospective_holdout import build_selection_lock, validate_holdout_candidate
from lola_prospective_result import ANCHOR_SHA, PREREGISTRATION_SEAL, REGISTRATION_ID


def digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ProspectiveSelectionLineageTests(unittest.TestCase):
    def _candidate(self) -> dict:
        value = {
            "schema_version": "prospective-holdout-candidate-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "CANDIDATE_CONSTRUCTION",
            "status": "CANDIDATE_READY_FOR_SELECTION_LOCK_REVIEW",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "failure_commit_sha": "1" * 40,
            "observation_digest_sha256": "a" * 64,
            "eligibility_review_digest_sha256": "b" * 64,
            "reviewer_id": "independent-reviewer-1",
            "observed_failure": {
                "surface": "workflow",
                "observable_failure": True,
                "naturally_occurring": True,
                "benchmark_authored": False,
                "intentionally_injected": False,
                "documentation_only": False,
                "test_only_fixture": False,
                "same_origin_training": False,
                "known_outcome_at_selection": False,
                "cherry_picked": False,
                "first_eligible_confirmed": True,
                "before_evidence_refs": ["ci:run-123"],
                "prior_post_anchor_failures_reviewed": [],
            },
            "candidate_constructed": True,
            "selection_authorized": False,
            "lock_authorized": False,
            "automated_repair_authorized": False,
            "repair_outcome": "UNKNOWN",
            "fix_commit_sha": None,
            "result_commit_sha": None,
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
            "candidate_boundary": "Candidate construction only",
        }
        value["candidate_digest_sha256"] = digest(value)
        return value

    def test_digest_bound_candidate_is_accepted_and_lineage_is_frozen_into_lock(self):
        candidate = self._candidate()
        verdict = validate_holdout_candidate(candidate, trust_ancestry_flag=True)
        self.assertTrue(verdict["valid_candidate"], verdict["reasons"])
        self.assertTrue(verdict["candidate_digest_verified"])

        lock = build_selection_lock(candidate, trust_ancestry_flag=True)
        self.assertEqual(lock["candidate_digest_sha256"], candidate["candidate_digest_sha256"])
        self.assertEqual(lock["observation_digest_sha256"], candidate["observation_digest_sha256"])
        self.assertEqual(lock["eligibility_review_digest_sha256"], candidate["eligibility_review_digest_sha256"])
        self.assertEqual(lock["eligibility_reviewer_id"], candidate["reviewer_id"])
        self.assertFalse(lock["prospective_claim"])

    def test_legacy_handcrafted_candidate_without_lineage_is_rejected(self):
        candidate = self._candidate()
        for field in (
            "phase",
            "status",
            "observation_digest_sha256",
            "eligibility_review_digest_sha256",
            "reviewer_id",
            "candidate_constructed",
            "selection_authorized",
            "lock_authorized",
            "automated_repair_authorized",
            "repair_outcome",
            "fix_commit_sha",
            "result_commit_sha",
            "candidate_digest_sha256",
        ):
            candidate.pop(field, None)

        verdict = validate_holdout_candidate(candidate, trust_ancestry_flag=True)
        self.assertFalse(verdict["valid_candidate"])
        self.assertIn("candidate_phase_invalid", verdict["reasons"])
        self.assertIn("candidate_status_invalid", verdict["reasons"])
        self.assertIn("candidate_digest_missing_or_invalid", verdict["reasons"])

    def test_tampering_after_candidate_digest_is_rejected(self):
        candidate = self._candidate()
        candidate["observed_failure"]["surface"] = "config"

        verdict = validate_holdout_candidate(candidate, trust_ancestry_flag=True)
        self.assertFalse(verdict["valid_candidate"])
        self.assertIn("candidate_digest_mismatch", verdict["reasons"])

    def test_candidate_must_still_be_pre_repair_and_without_authority(self):
        candidate = self._candidate()
        candidate["repair_outcome"] = "FIXED"
        candidate["fix_commit_sha"] = "2" * 40
        candidate["selection_authorized"] = True
        candidate["candidate_digest_sha256"] = digest({k: v for k, v in candidate.items() if k != "candidate_digest_sha256"})

        verdict = validate_holdout_candidate(candidate, trust_ancestry_flag=True)
        self.assertFalse(verdict["valid_candidate"])
        self.assertIn("candidate_repair_outcome_known", verdict["reasons"])
        self.assertIn("candidate_fix_already_known", verdict["reasons"])
        self.assertIn("candidate_selection_boundary_broken", verdict["reasons"])


if __name__ == "__main__":
    unittest.main()

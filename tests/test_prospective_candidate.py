import hashlib
import json
import unittest

from lola_prospective_result import ANCHOR_SHA, PREREGISTRATION_SEAL, REGISTRATION_ID
from lola_prospective_candidate import build_candidate


def digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ProspectiveCandidateTests(unittest.TestCase):
    def _observation(self) -> dict:
        value = {
            "schema_version": "prospective-holdout-observation-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "OBSERVER",
            "status": "OBSERVED_REVIEW_REQUIRED",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "observation_created": True,
            "selection_authorized": False,
            "lock_authorized": False,
            "automated_repair_authorized": False,
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
            "failure_commit_sha": "1" * 40,
            "git_ancestry_verified": True,
            "source": "github_workflow_run",
            "workflow_run": {
                "id": 4242,
                "name": "Toolchain smoke check",
                "head_branch": "feature/example",
                "trigger_event": "push",
                "status": "completed",
                "conclusion": "failure",
                "run_url": "https://github.com/example/lola/actions/runs/4242",
                "run_started_at": "2026-10-02T10:00:00Z",
                "updated_at": "2026-10-02T10:01:00Z",
            },
            "before_evidence_refs": ["https://github.com/example/lola/actions/runs/4242"],
            "review_fields": {
                "surface": None,
                "naturally_occurring": None,
                "benchmark_authored": None,
                "intentionally_injected": None,
                "documentation_only": None,
                "test_only_fixture": None,
                "same_origin_training": None,
                "known_outcome_at_selection": None,
                "cherry_picked": None,
                "first_eligible_confirmed": None,
                "prior_post_anchor_failures_reviewed": None,
            },
            "repair_outcome": "UNKNOWN",
            "observer_boundary": "Observation only",
        }
        value["observation_digest_sha256"] = digest(value)
        return value

    def _verdict(self, observation: dict, *, status: str = "REVIEW_ELIGIBLE") -> dict:
        fields = {
            "surface": "workflow",
            "naturally_occurring": True,
            "benchmark_authored": False,
            "intentionally_injected": False,
            "documentation_only": False,
            "test_only_fixture": False,
            "same_origin_training": False,
            "known_outcome_at_selection": False,
            "cherry_picked": False,
            "first_eligible_confirmed": True,
            "prior_post_anchor_failures_reviewed": [],
        }
        value = {
            "schema_version": "prospective-holdout-eligibility-verdict-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "ELIGIBILITY_REVIEW",
            "status": status,
            "valid_review": status == "REVIEW_ELIGIBLE",
            "observation_digest_sha256": observation["observation_digest_sha256"],
            "failure_commit_sha": observation["failure_commit_sha"],
            "reviewer_id": "independent-reviewer-1",
            "reviewer_independent": True,
            "review_completed_before_repair": True,
            "review_fields": fields,
            "reasons": [] if status == "REVIEW_ELIGIBLE" else ["not_first_eligible"],
            "repair_outcome": "UNKNOWN",
            "candidate_authorized": False,
            "selection_authorized": False,
            "lock_authorized": False,
            "automated_repair_authorized": False,
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
            "review_boundary": "Eligibility classification only",
        }
        value["eligibility_review_digest_sha256"] = digest(value)
        return value

    def test_eligible_review_builds_candidate_but_does_not_authorize_lock_or_repair(self):
        observation = self._observation()
        verdict = self._verdict(observation)

        candidate = build_candidate(observation, verdict)

        self.assertEqual(candidate["schema_version"], "prospective-holdout-candidate-v1")
        self.assertEqual(candidate["status"], "CANDIDATE_READY_FOR_SELECTION_LOCK_REVIEW")
        self.assertEqual(candidate["failure_commit_sha"], observation["failure_commit_sha"])
        self.assertTrue(candidate["candidate_constructed"])
        self.assertFalse(candidate["selection_authorized"])
        self.assertFalse(candidate["lock_authorized"])
        self.assertFalse(candidate["automated_repair_authorized"])
        self.assertFalse(candidate["prospective_claim"])
        self.assertFalse(candidate["blind_holdout_claim"])
        self.assertFalse(candidate["production_world_claim"])
        self.assertEqual(candidate["observed_failure"]["surface"], "workflow")
        self.assertTrue(candidate["observed_failure"]["observable_failure"])
        self.assertEqual(candidate["observed_failure"]["before_evidence_refs"], observation["before_evidence_refs"])
        self.assertRegex(candidate["candidate_digest_sha256"], r"^[0-9a-f]{64}$")

    def test_rejected_review_cannot_construct_candidate(self):
        observation = self._observation()
        verdict = self._verdict(observation, status="REVIEW_REJECTED")

        with self.assertRaises(ValueError):
            build_candidate(observation, verdict)

    def test_tampered_observation_is_rejected_even_with_old_eligible_verdict(self):
        observation = self._observation()
        verdict = self._verdict(observation)
        observation["before_evidence_refs"].append("tampered")

        with self.assertRaises(ValueError):
            build_candidate(observation, verdict)

    def test_tampered_or_mismatched_verdict_is_rejected(self):
        observation = self._observation()
        verdict = self._verdict(observation)
        verdict["failure_commit_sha"] = "2" * 40

        with self.assertRaises(ValueError):
            build_candidate(observation, verdict)


if __name__ == "__main__":
    unittest.main()

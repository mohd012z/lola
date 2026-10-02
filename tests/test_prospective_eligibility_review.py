import hashlib
import json
import unittest

from lola_prospective_eligibility_review import review_observation
from lola_prospective_result import ANCHOR_SHA, PREREGISTRATION_SEAL, REGISTRATION_ID


def canonical_digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ProspectiveEligibilityReviewTests(unittest.TestCase):
    def _observation(self):
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
            "observer_boundary": "observation only",
        }
        value["observation_digest_sha256"] = canonical_digest(value)
        return value

    def _review(self, observation):
        return {
            "schema_version": "prospective-holdout-eligibility-review-v1",
            "registration_id": REGISTRATION_ID,
            "observation_digest_sha256": observation["observation_digest_sha256"],
            "reviewer_id": "independent-reviewer-01",
            "reviewer_independent": True,
            "review_completed_before_repair": True,
            "review_fields": {
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
            },
        }

    def test_valid_independent_review_is_eligible_but_cannot_select_or_lock(self):
        observation = self._observation()
        result = review_observation(observation, self._review(observation))

        self.assertTrue(result["valid_review"])
        self.assertEqual(result["status"], "REVIEW_ELIGIBLE")
        self.assertFalse(result["selection_authorized"])
        self.assertFalse(result["lock_authorized"])
        self.assertFalse(result["automated_repair_authorized"])
        self.assertFalse(result["prospective_claim"])
        self.assertFalse(result["blind_holdout_claim"])
        self.assertFalse(result["production_world_claim"])
        self.assertEqual(result["repair_outcome"], "UNKNOWN")
        self.assertRegex(result["eligibility_review_digest_sha256"], r"^[0-9a-f]{64}$")

    def test_tampered_observation_is_rejected(self):
        observation = self._observation()
        review = self._review(observation)
        observation["workflow_run"]["name"] = "changed after observation"

        result = review_observation(observation, review)

        self.assertFalse(result["valid_review"])
        self.assertEqual(result["status"], "REVIEW_REJECTED")
        self.assertIn("observation_digest_mismatch", result["reasons"])

    def test_non_independent_or_post_repair_review_is_rejected(self):
        observation = self._observation()
        review = self._review(observation)
        review["reviewer_independent"] = False
        review["review_completed_before_repair"] = False

        result = review_observation(observation, review)

        self.assertFalse(result["valid_review"])
        self.assertIn("reviewer_not_independent", result["reasons"])
        self.assertIn("review_not_completed_before_repair", result["reasons"])

    def test_known_outcome_or_cherry_pick_is_rejected(self):
        observation = self._observation()
        review = self._review(observation)
        review["review_fields"]["known_outcome_at_selection"] = True
        review["review_fields"]["cherry_picked"] = True

        result = review_observation(observation, review)

        self.assertFalse(result["valid_review"])
        self.assertIn("outcome_known_at_review", result["reasons"])
        self.assertIn("cherry_pick_forbidden", result["reasons"])

    def test_review_never_creates_candidate_or_selection_lock(self):
        observation = self._observation()
        result = review_observation(observation, self._review(observation))

        self.assertNotIn("observed_failure", result)
        self.assertNotIn("selection", result)
        self.assertNotIn("selection_lock_digest_sha256", result)
        self.assertFalse(result.get("candidate_authorized", False))


if __name__ == "__main__":
    unittest.main()

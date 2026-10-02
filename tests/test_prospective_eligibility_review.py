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
                "run_attempt": 1,
                "name": "Toolchain smoke check",
                "head_branch": "feature/example",
                "trigger_event": "push",
                "status": "completed",
                "conclusion": "failure",
                "run_url": "https://github.com/example/lola/actions/runs/4242",
                "run_api_url": "https://api.github.com/repos/example/lola/actions/runs/4242",
                "attempt_api_url": "https://api.github.com/repos/example/lola/actions/runs/4242/attempts/1",
                "run_started_at": "2026-10-02T10:00:00Z",
                "updated_at": "2026-10-02T10:01:00Z",
            },
            "before_evidence_refs": ["https://api.github.com/repos/example/lola/actions/runs/4242/attempts/1"],
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

    def _census(self, observation):
        event = {
            "event_key": "2026-10-02T10:00:00Z|00000000000000004242|000001",
            "run_id": 4242,
            "run_attempt": 1,
            "head_sha": observation["failure_commit_sha"],
            "workflow_name": "Toolchain smoke check",
            "conclusion": "failure",
            "run_started_at": "2026-10-02T10:00:00Z",
            "updated_at": "2026-10-02T10:01:00Z",
            "attempt_api_url": observation["workflow_run"]["attempt_api_url"],
        }
        census = {
            "schema_version": "prospective-event-census-v1",
            "registration_id": REGISTRATION_ID,
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "source": "github_actions_history",
            "candidate_event_key": event["event_key"],
            "ordered_events": [event],
            "history_complete_through_candidate": True,
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
        }
        census["event_census_digest_sha256"] = canonical_digest(census)
        return census

    def _review(self, observation):
        return {
            "schema_version": "prospective-holdout-eligibility-review-v1",
            "registration_id": REGISTRATION_ID,
            "observation_digest_sha256": observation["observation_digest_sha256"],
            "reviewer_id": "independent-reviewer-01",
            "reviewer_independent": True,
            "review_completed_before_repair": True,
            "event_census": self._census(observation),
            "prior_event_verdicts": [],
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
        self.assertRegex(result["event_census_digest_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["eligibility_review_digest_sha256"], r"^[0-9a-f]{64}$")

    def test_missing_census_proof_is_rejected(self):
        observation = self._observation()
        review = self._review(observation)
        review.pop("event_census")

        result = review_observation(observation, review)

        self.assertFalse(result["valid_review"])
        self.assertIn("event_census_missing", result["reasons"])

    def test_census_with_unreviewed_earlier_event_is_rejected(self):
        observation = self._observation()
        review = self._review(observation)
        earlier = {
            "event_key": "2026-10-02T09:00:00Z|00000000000000004000|000001",
            "run_id": 4000,
            "run_attempt": 1,
            "head_sha": "2" * 40,
            "workflow_name": "Lola Code Doctor",
            "conclusion": "failure",
            "run_started_at": "2026-10-02T09:00:00Z",
            "updated_at": "2026-10-02T09:01:00Z",
            "attempt_api_url": "https://api.github.com/repos/example/lola/actions/runs/4000/attempts/1",
        }
        census = review["event_census"]
        census["ordered_events"].insert(0, earlier)
        census.pop("event_census_digest_sha256")
        census["event_census_digest_sha256"] = canonical_digest(census)

        result = review_observation(observation, review)

        self.assertFalse(result["valid_review"])
        self.assertIn("prior_event_unreviewed", result["reasons"])

    def test_rejected_prior_event_allows_candidate_to_be_derived_first_eligible(self):
        observation = self._observation()
        review = self._review(observation)
        earlier = {
            "event_key": "2026-10-02T09:00:00Z|00000000000000004000|000001",
            "run_id": 4000,
            "run_attempt": 1,
            "head_sha": "2" * 40,
            "workflow_name": "Lola Code Doctor",
            "conclusion": "failure",
            "run_started_at": "2026-10-02T09:00:00Z",
            "updated_at": "2026-10-02T09:01:00Z",
            "attempt_api_url": "https://api.github.com/repos/example/lola/actions/runs/4000/attempts/1",
        }
        census = review["event_census"]
        census["ordered_events"].insert(0, earlier)
        census.pop("event_census_digest_sha256")
        census["event_census_digest_sha256"] = canonical_digest(census)
        review["prior_event_verdicts"] = [
            {
                "event_key": earlier["event_key"],
                "status": "REVIEW_REJECTED",
                "eligibility_review_digest_sha256": "a" * 64,
            }
        ]
        review["review_fields"]["prior_post_anchor_failures_reviewed"] = [earlier["event_key"]]

        result = review_observation(observation, review)

        self.assertTrue(result["valid_review"])
        self.assertEqual(result["status"], "REVIEW_ELIGIBLE")

    def test_tampered_census_is_rejected(self):
        observation = self._observation()
        review = self._review(observation)
        review["event_census"]["ordered_events"][0]["run_id"] = 9999

        result = review_observation(observation, review)

        self.assertFalse(result["valid_review"])
        self.assertIn("event_census_digest_mismatch", result["reasons"])

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

import json
import tempfile
import unittest
from pathlib import Path

from lola_prospective_eligibility_review import main
from lola_prospective_result import ANCHOR_SHA, PREREGISTRATION_SEAL, REGISTRATION_ID


class ProspectiveEligibilityReviewCliTests(unittest.TestCase):
    def test_cli_writes_verdict_only_and_never_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            observation = {
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
                "workflow_run": {"conclusion": "failure"},
                "before_evidence_refs": ["run:1"],
                "review_fields": {},
                "repair_outcome": "UNKNOWN",
                "observer_boundary": "observation only",
            }
            import hashlib
            payload = json.dumps(observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            observation["observation_digest_sha256"] = hashlib.sha256(payload).hexdigest()
            review = {
                "schema_version": "prospective-holdout-eligibility-review-v1",
                "registration_id": REGISTRATION_ID,
                "observation_digest_sha256": observation["observation_digest_sha256"],
                "reviewer_id": "reviewer-1",
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
            observation_path = root / "observation.json"
            review_path = root / "review.json"
            output_path = root / "verdict.json"
            observation_path.write_text(json.dumps(observation), encoding="utf-8")
            review_path.write_text(json.dumps(review), encoding="utf-8")

            rc = main([str(observation_path), str(review_path), "--output", str(output_path)])

            self.assertEqual(rc, 0)
            verdict = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(verdict["status"], "REVIEW_ELIGIBLE")
            self.assertFalse(verdict["selection_authorized"])
            self.assertFalse(verdict["lock_authorized"])
            self.assertNotIn("selection_lock_digest_sha256", verdict)


if __name__ == "__main__":
    unittest.main()

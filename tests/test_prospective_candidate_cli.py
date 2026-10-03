import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lola_prospective_result import ANCHOR_SHA, PREREGISTRATION_SEAL, REGISTRATION_ID


ROOT = Path(__file__).resolve().parents[1]


def digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ProspectiveCandidateCliTests(unittest.TestCase):
    def _pair(self, eligible: bool = True) -> tuple[dict, dict]:
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
            "before_evidence_refs": ["github-actions-run:4242"],
            "review_fields": {},
            "repair_outcome": "UNKNOWN",
            "observer_boundary": "Observation only",
        }
        observation["observation_digest_sha256"] = digest(observation)

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
        status = "REVIEW_ELIGIBLE" if eligible else "REVIEW_REJECTED"
        verdict = {
            "schema_version": "prospective-holdout-eligibility-verdict-v1",
            "registration_id": REGISTRATION_ID,
            "phase": "ELIGIBILITY_REVIEW",
            "status": status,
            "valid_review": eligible,
            "observation_digest_sha256": observation["observation_digest_sha256"],
            "failure_commit_sha": observation["failure_commit_sha"],
            "reviewer_id": "independent-reviewer-1",
            "reviewer_independent": True,
            "review_completed_before_repair": True,
            "review_fields": fields,
            "reasons": [] if eligible else ["not_first_eligible"],
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
        verdict["eligibility_review_digest_sha256"] = digest(verdict)
        return observation, verdict

    def test_cli_writes_candidate_only_for_eligible_review(self):
        observation, verdict = self._pair(True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obs_path = root / "observation.json"
            verdict_path = root / "verdict.json"
            out_path = root / "candidate.json"
            obs_path.write_text(json.dumps(observation), encoding="utf-8")
            verdict_path.write_text(json.dumps(verdict), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "lola_prospective_candidate.py"),
                    str(obs_path),
                    str(verdict_path),
                    "--output",
                    str(out_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "CANDIDATE_READY_FOR_SELECTION_LOCK_REVIEW")
            self.assertFalse(payload["selection_authorized"])
            self.assertFalse(payload["lock_authorized"])
            self.assertFalse(payload["automated_repair_authorized"])
            self.assertIsNone(payload["fix_commit_sha"])
            self.assertIsNone(payload["result_commit_sha"])

    def test_cli_rejected_review_writes_no_candidate(self):
        observation, verdict = self._pair(False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obs_path = root / "observation.json"
            verdict_path = root / "verdict.json"
            out_path = root / "candidate.json"
            obs_path.write_text(json.dumps(observation), encoding="utf-8")
            verdict_path.write_text(json.dumps(verdict), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "lola_prospective_candidate.py"),
                    str(obs_path),
                    str(verdict_path),
                    "--output",
                    str(out_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(out_path.exists())


if __name__ == "__main__":
    unittest.main()

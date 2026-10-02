import subprocess
import tempfile
import unittest
from pathlib import Path

from lola_prospective_holdout_observer import observe_workflow_event


class ProspectiveHoldoutObserverTests(unittest.TestCase):
    def _event(self, head_sha: str, conclusion: str = "failure") -> dict:
        return {
            "action": "completed",
            "workflow_run": {
                "id": 4242,
                "name": "Toolchain smoke check",
                "head_sha": head_sha,
                "head_branch": "feature/example",
                "event": "push",
                "status": "completed",
                "conclusion": conclusion,
                "html_url": "https://github.com/example/lola/actions/runs/4242",
                "run_started_at": "2026-10-02T10:00:00Z",
                "updated_at": "2026-10-02T10:01:00Z",
            },
        }

    def _repo_with_anchor_and_failure(self):
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "LOLA Test"], check=True)

        (repo / "state.txt").write_text("anchor", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "state.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "anchor"], check=True)
        anchor = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

        (repo / "state.txt").write_text("failure", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "state.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "failure"], check=True)
        failure = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        return tmp, repo, anchor, failure

    def test_failed_post_anchor_workflow_becomes_review_required_observation_only(self):
        tmp, repo, anchor, failure = self._repo_with_anchor_and_failure()
        self.addCleanup(tmp.cleanup)

        result = observe_workflow_event(
            self._event(failure),
            repository_root=repo,
            expected_anchor_sha=anchor,
        )

        self.assertEqual(result["status"], "OBSERVED_REVIEW_REQUIRED")
        self.assertEqual(result["phase"], "OBSERVER")
        self.assertTrue(result["git_ancestry_verified"])
        self.assertEqual(result["failure_commit_sha"], failure)
        self.assertEqual(result["repair_outcome"], "UNKNOWN")
        self.assertFalse(result["selection_authorized"])
        self.assertFalse(result["lock_authorized"])
        self.assertFalse(result["automated_repair_authorized"])
        self.assertFalse(result["prospective_claim"])
        self.assertFalse(result["blind_holdout_claim"])
        self.assertFalse(result["production_world_claim"])
        self.assertIsNone(result["review_fields"]["naturally_occurring"])
        self.assertIsNone(result["review_fields"]["benchmark_authored"])
        self.assertIsNone(result["review_fields"]["first_eligible_confirmed"])
        self.assertRegex(result["observation_digest_sha256"], r"^[0-9a-f]{64}$")

    def test_successful_workflow_is_ignored_and_never_becomes_candidate(self):
        tmp, repo, anchor, failure = self._repo_with_anchor_and_failure()
        self.addCleanup(tmp.cleanup)

        result = observe_workflow_event(
            self._event(failure, conclusion="success"),
            repository_root=repo,
            expected_anchor_sha=anchor,
        )

        self.assertEqual(result["status"], "IGNORED_NOT_FAILURE")
        self.assertFalse(result["observation_created"])
        self.assertFalse(result["selection_authorized"])
        self.assertFalse(result["lock_authorized"])

    def test_anchor_or_pre_anchor_failure_is_ignored(self):
        tmp, repo, anchor, _failure = self._repo_with_anchor_and_failure()
        self.addCleanup(tmp.cleanup)

        result = observe_workflow_event(
            self._event(anchor),
            repository_root=repo,
            expected_anchor_sha=anchor,
        )

        self.assertEqual(result["status"], "IGNORED_NOT_POST_ANCHOR")
        self.assertFalse(result["git_ancestry_verified"])
        self.assertFalse(result["observation_created"])
        self.assertFalse(result["selection_authorized"])

    def test_observer_never_asserts_eligibility_fields(self):
        tmp, repo, anchor, failure = self._repo_with_anchor_and_failure()
        self.addCleanup(tmp.cleanup)

        result = observe_workflow_event(
            self._event(failure),
            repository_root=repo,
            expected_anchor_sha=anchor,
        )

        expected_unknowns = {
            "surface",
            "naturally_occurring",
            "benchmark_authored",
            "intentionally_injected",
            "documentation_only",
            "test_only_fixture",
            "same_origin_training",
            "known_outcome_at_selection",
            "cherry_picked",
            "first_eligible_confirmed",
            "prior_post_anchor_failures_reviewed",
        }
        self.assertEqual(set(result["review_fields"]), expected_unknowns)
        self.assertTrue(all(value is None for value in result["review_fields"].values()))


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


class ProspectiveHoldoutObserverWorkflowTests(unittest.TestCase):
    def test_workflow_is_observer_only_and_does_not_execute_failed_head_code(self):
        repo = Path(__file__).resolve().parents[1]
        path = repo / ".github" / "workflows" / "prospective-holdout-observer.yml"
        text = path.read_text(encoding="utf-8")

        self.assertIn("name: Prospective holdout observer", text)
        self.assertIn("workflow_run:", text)
        self.assertIn('"Toolchain smoke check"', text)
        self.assertIn('"Lola Code Doctor"', text)
        self.assertIn("types: [completed]", text)
        self.assertIn("github.event.workflow_run.conclusion == 'failure'", text)
        self.assertIn("contents: read", text)
        self.assertNotIn("contents: write", text)

        # Trusted code is checked out from the repository default branch.
        self.assertIn("github.event.repository.default_branch", text)
        self.assertNotIn("ref: ${{ github.event.workflow_run.head_sha }}", text)

        # The failed SHA may be fetched as Git evidence, but is never checked out or executed.
        self.assertIn("github.event.workflow_run.head_sha", text)
        self.assertIn("git fetch", text)
        self.assertIn("--prospective-holdout-observe", text)
        self.assertIn("$GITHUB_EVENT_PATH", text)
        self.assertIn("actions/upload-artifact@v4", text)

        # Hard boundary: the observer cannot select/lock/repair or mutate repository state.
        self.assertNotIn("--prospective-holdout-lock", text)
        self.assertNotIn("--holdout-lock-output", text)
        self.assertNotIn("git commit", text)
        self.assertNotIn("git push", text)
        self.assertNotIn("pull_request", text)


if __name__ == "__main__":
    unittest.main()

# Integration contract: pin complete rerun-attempt history plus real post-anchor ancestry.
import inspect
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import lola_prospective_event_census as census


class ProspectiveEventCensusGenerationTests(unittest.TestCase):
    def _commit(self, repo: Path, name: str) -> str:
        target = repo / "state.txt"
        target.write_text(name + "\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "state.txt"], check=True)
        env = os.environ.copy()
        env.update(
            {
                "GIT_AUTHOR_NAME": "LOLA Test",
                "GIT_AUTHOR_EMAIL": "lola@example.invalid",
                "GIT_COMMITTER_NAME": "LOLA Test",
                "GIT_COMMITTER_EMAIL": "lola@example.invalid",
            }
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", name],
            check=True,
            stdout=subprocess.DEVNULL,
            env=env,
        )
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()

    def _run(self, *, run_id: int, attempt: int, sha: str, conclusion: str, started: str):
        return {
            "id": run_id,
            "run_attempt": attempt,
            "head_sha": sha,
            "name": "Toolchain smoke check",
            "conclusion": conclusion,
            "run_started_at": started,
            "updated_at": started,
            "url": f"https://api.github.com/repos/example/lola/actions/runs/{run_id}",
        }

    def test_builder_requires_repository_root_and_filters_pre_anchor_events(self):
        parameters = inspect.signature(census.build_event_census).parameters
        self.assertIn("repository_root", parameters)
        self.assertIn("expected_anchor_sha", parameters)
        if "repository_root" not in parameters or "expected_anchor_sha" not in parameters:
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            pre_anchor = self._commit(repo, "pre-anchor")
            anchor = self._commit(repo, "anchor")
            candidate_sha = self._commit(repo, "candidate")

            history = [
                self._run(
                    run_id=100,
                    attempt=1,
                    sha=pre_anchor,
                    conclusion="failure",
                    started="2026-10-02T09:00:00Z",
                ),
                self._run(
                    run_id=200,
                    attempt=1,
                    sha=candidate_sha,
                    conclusion="failure",
                    started="2026-10-02T10:00:00Z",
                ),
            ]

            result = census.build_event_census(
                history,
                candidate_run_id=200,
                candidate_run_attempt=1,
                history_complete=True,
                repository_root=repo,
                expected_anchor_sha=anchor,
            )

            self.assertEqual([event["run_id"] for event in result["ordered_events"]], [200])
            self.assertTrue(result["ordered_events"][0]["git_ancestry_verified"])

    def test_history_expansion_preserves_failed_attempt_before_successful_rerun(self):
        self.assertTrue(hasattr(census, "expand_workflow_attempt_history"))
        if not hasattr(census, "expand_workflow_attempt_history"):
            return

        latest = {
            "id": 300,
            "run_attempt": 2,
            "head_sha": "3" * 40,
            "name": "Toolchain smoke check",
            "conclusion": "success",
            "run_started_at": "2026-10-02T11:00:00Z",
            "updated_at": "2026-10-02T11:05:00Z",
            "url": "https://api.github.com/repos/example/lola/actions/runs/300",
        }
        attempt_payloads = {
            1: {**latest, "run_attempt": 1, "conclusion": "failure", "updated_at": "2026-10-02T11:02:00Z"},
            2: latest,
        }
        requested = []

        def fetch_attempt(run_id: int, attempt: int):
            requested.append((run_id, attempt))
            return attempt_payloads[attempt]

        expanded = census.expand_workflow_attempt_history([latest], fetch_attempt=fetch_attempt)

        self.assertEqual(requested, [(300, 1), (300, 2)])
        self.assertEqual([(item["run_attempt"], item["conclusion"]) for item in expanded], [(1, "failure"), (2, "success")])

    def test_builder_order_is_deterministic_across_runs_and_attempts(self):
        events = [
            self._run(run_id=9, attempt=2, sha="9" * 40, conclusion="failure", started="2026-10-02T10:00:00Z"),
            self._run(run_id=8, attempt=1, sha="8" * 40, conclusion="failure", started="2026-10-02T10:00:00Z"),
            self._run(run_id=9, attempt=1, sha="9" * 40, conclusion="failure", started="2026-10-02T10:00:00Z"),
        ]
        result = census.build_event_census(
            events,
            candidate_run_id=9,
            candidate_run_attempt=2,
            history_complete=True,
            trust_post_anchor_flag=True,
        )
        self.assertEqual(
            [(item["run_id"], item["run_attempt"]) for item in result["ordered_events"]],
            [(8, 1), (9, 1), (9, 2)],
        )

    def test_observer_workflow_uses_read_only_actions_and_expands_attempts(self):
        repo_root = Path(__file__).resolve().parents[1]
        workflow = (repo_root / ".github/workflows/prospective-holdout-observer.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertIn("actions: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("expand_workflow_attempt_history", workflow)
        self.assertIn("/attempts/", workflow)
        self.assertIn("repository_root=Path(\".\")", workflow)
        self.assertIn("git fetch --no-tags origin", workflow)


if __name__ == "__main__":
    unittest.main()

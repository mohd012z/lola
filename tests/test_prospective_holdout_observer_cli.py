import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lola import main


class ProspectiveHoldoutObserverCliTests(unittest.TestCase):
    def test_cli_writes_review_required_observation_without_selection(self):
        repo = Path(__file__).resolve().parents[1]
        head_sha = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
        event = {
            "action": "completed",
            "workflow_run": {
                "id": 9001,
                "name": "Toolchain smoke check",
                "head_sha": head_sha,
                "head_branch": "feature/example",
                "event": "push",
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://github.com/example/lola/actions/runs/9001",
                "run_started_at": "2026-10-02T10:00:00Z",
                "updated_at": "2026-10-02T10:01:00Z",
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "workflow-event.json"
            output_path = Path(tmp) / "observation.json"
            event_path.write_text(json.dumps(event), encoding="utf-8")

            argv = [
                "lola.py",
                "--prospective-holdout-observe",
                str(event_path),
                "--holdout-observation-output",
                str(output_path),
            ]
            with mock.patch.object(sys, "argv", argv):
                rc = main()

            self.assertEqual(rc, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "OBSERVED_REVIEW_REQUIRED")
            self.assertFalse(payload["selection_authorized"])
            self.assertFalse(payload["lock_authorized"])
            self.assertFalse(payload["automated_repair_authorized"])
            self.assertNotIn("selection_lock_digest_sha256", payload)

    def test_output_option_cannot_be_used_without_observer_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            argv = [
                "lola.py",
                "--holdout-observation-output",
                str(Path(tmp) / "observation.json"),
            ]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    main()
            self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

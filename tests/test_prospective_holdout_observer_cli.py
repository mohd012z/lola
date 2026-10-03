import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lola import main


class ProspectiveHoldoutObserverCliTests(unittest.TestCase):
    def test_cli_writes_review_required_observation_without_selection(self):
        event = {
            "action": "completed",
            "workflow_run": {
                "id": 9001,
                "name": "Toolchain smoke check",
                "head_sha": "1" * 40,
                "status": "completed",
                "conclusion": "failure",
            },
        }
        observed = {
            "schema_version": "prospective-holdout-observation-v1",
            "phase": "OBSERVER",
            "status": "OBSERVED_REVIEW_REQUIRED",
            "observation_created": True,
            "failure_commit_sha": "1" * 40,
            "git_ancestry_verified": True,
            "repair_outcome": "UNKNOWN",
            "selection_authorized": False,
            "lock_authorized": False,
            "automated_repair_authorized": False,
            "prospective_claim": False,
            "blind_holdout_claim": False,
            "production_world_claim": False,
            "review_fields": {"first_eligible_confirmed": None},
            "observation_digest_sha256": "a" * 64,
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
            with mock.patch.object(sys, "argv", argv), mock.patch(
                "lola_prospective_holdout_observer.observe_workflow_event",
                return_value=observed,
            ) as observer:
                rc = main()

            self.assertEqual(rc, 0)
            observer.assert_called_once()
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

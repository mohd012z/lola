from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lola_handoff_adapter as handoff


class LolaHandoffAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "src").mkdir()
        (self.project / "src" / "main.js").write_text("console.log('ok')\n", encoding="utf-8")
        self.apk = self.project / "sample.apk"
        self.apk.write_bytes(b"PK\x03\x04demo")
        self.manifest = self.root / "job.json"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def base_manifest(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "contractVersion": handoff.CONTRACT_VERSION,
            "jobId": "job-001",
            "source": "myai",
            "target": "lola",
            "taskType": "security-scan",
            "request": "Run a local security scan only.",
            "project": {"id": "proj-1", "name": "Demo", "rootPath": str(self.project)},
            "selectedFiles": [{"path": "src/main.js", "size": 18}],
            "options": {"noOpen": True},
            "authorization": {"confirmed": True, "scope": "user-owned-or-authorized-project"},
            "createdAt": "2026-09-24T04:00:00Z",
        }
        payload.update(overrides)
        return payload

    def write_manifest(self, payload: dict[str, object]) -> Path:
        self.manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.manifest

    def test_validate_manifest_accepts_contract_v1(self) -> None:
        validated, warnings = handoff.validate_manifest(self.base_manifest(), self.manifest)

        self.assertEqual(validated["jobId"], "job-001")
        self.assertEqual(validated["taskType"], "security-scan")
        self.assertEqual(validated["executionTarget"], self.project / "src" / "main.js")
        self.assertEqual(warnings, [])

    def test_validate_manifest_rejects_result_traversal(self) -> None:
        manifest = self.base_manifest(options={"resultPath": "../escape.json"})

        with self.assertRaisesRegex(handoff.HandoffError, "manifest directory"):
            handoff.validate_manifest(manifest, self.manifest)

    def test_validate_manifest_rejects_selected_file_traversal(self) -> None:
        manifest = self.base_manifest(selectedFiles=[{"path": "../secret.txt", "size": 1}])

        with self.assertRaisesRegex(handoff.HandoffError, "inside the project root"):
            handoff.validate_manifest(manifest, self.manifest)

    def test_bounded_load_rejects_oversized_manifest(self) -> None:
        too_large = self.root / "too-large.json"
        too_large.write_text("x" * (handoff.MAX_MANIFEST_BYTES + 1), encoding="utf-8")

        with self.assertRaisesRegex(handoff.HandoffError, "exceeds"):
            handoff.bounded_load_manifest(too_large)

    def test_execute_handoff_serializes_completed_result(self) -> None:
        self.write_manifest(
            self.base_manifest(
                taskType="deep-dive",
                selectedFiles=[{"path": "sample.apk", "size": self.apk.stat().st_size}],
            )
        )

        artifact_dir = self.root / "job-001-artifacts"
        artifact_dir.mkdir()
        analysis = artifact_dir / "apk-analysis.json"
        report = artifact_dir / "apk-report.html"
        analysis.write_text('{"ok":true}', encoding="utf-8")
        report.write_text("<html></html>", encoding="utf-8")

        with patch.object(
            handoff,
            "_execute_apk_scan",
            return_value=(0, {"apk-analysis.json": str(analysis), "apk-report.html": str(report)}, []),
        ):
            result = handoff.execute_handoff_manifest(self.manifest)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["provider"], handoff.PROVIDER)
        self.assertTrue(Path(result["resultPath"]).exists())
        persisted = json.loads(Path(result["resultPath"]).read_text(encoding="utf-8"))
        self.assertEqual(persisted["contractVersion"], handoff.CONTRACT_VERSION)
        self.assertEqual(persisted["jobId"], "job-001")
        self.assertEqual(persisted["status"], "completed")
        self.assertTrue(any(x["path"].endswith("apk-report.html") for x in persisted["artifacts"]))

    def test_execute_handoff_returns_partial_planning_fallback(self) -> None:
        self.write_manifest(self.base_manifest())

        with patch.object(
            handoff,
            "_execute_project_scan",
            return_value=(3, {}, ["PowerShell scan unavailable"]),
        ):
            result = handoff.execute_handoff_manifest(self.manifest)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["provider"], handoff.PLANNER_PROVIDER)
        self.assertIn("fallback", " ".join(result["warnings"]).lower())
        self.assertTrue(result["sections"])

    def test_execute_handoff_marks_unsupported_task(self) -> None:
        self.write_manifest(self.base_manifest(taskType="apk-creator"))

        result = handoff.execute_handoff_manifest(self.manifest)

        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["provider"], handoff.PLANNER_PROVIDER)

    def test_validate_cli_returns_machine_readable_error(self) -> None:
        self.write_manifest({"contractVersion": "9.9"})

        payload, code = handoff.validate_handoff_manifest(self.manifest)

        self.assertFalse(payload["ok"])
        self.assertEqual(code, handoff.EXIT_INVALID)
        self.assertIn("contractVersion", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()

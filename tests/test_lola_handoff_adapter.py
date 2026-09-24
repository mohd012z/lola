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
        self.target = self.root / "sample-project"
        self.target.mkdir()
        self.manifest_path = self.root / "handoff.json"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_manifest(self, payload: dict) -> Path:
        self.manifest_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        return self.manifest_path

    def base_manifest(self, **job_overrides: object) -> dict:
        job = {
            "id": "job-001",
            "type": "development",
            "target": {"path": str(self.target)},
            "lola": {"options": {"noOpen": True}},
        }
        job.update(job_overrides)
        return {
            "schema": handoff.JOB_SCHEMA,
            "sender": {"app": "msa_one", "workflow": "manual"},
            "job": job,
        }

    def test_validate_manifest_accepts_qwen_config_and_result_path(self) -> None:
        manifest = self.base_manifest()
        manifest["assistantConfig"] = {
            "provider": "qwen-compatible",
            "baseUrl": "http://127.0.0.1:8000/v1",
            "model": "qwen2.5-coder-7b-instruct",
            "apiKeyEnv": "QWEN_API_KEY",
        }
        manifest["result"] = {"path": "results/job-001.json"}

        validated, warnings = handoff.validate_manifest(manifest, self.manifest_path)

        self.assertEqual(validated["job"]["type"], "development")
        self.assertEqual(validated["assistantConfig"]["provider"], "qwen-compatible")
        self.assertEqual(validated["resultPath"], self.root / "results" / "job-001.json")
        self.assertEqual(warnings, [])

    def test_validate_manifest_rejects_unsafe_relative_result_path(self) -> None:
        manifest = self.base_manifest()
        manifest["result"] = {"path": "../escape/result.json"}

        with self.assertRaisesRegex(handoff.ManifestError, "manifest directory"):
            handoff.validate_manifest(manifest, self.manifest_path)

    def test_bounded_load_rejects_oversized_manifest(self) -> None:
        oversized = self.root / "too-large.json"
        oversized.write_text("x" * (handoff.MAX_MANIFEST_BYTES + 1), encoding="utf-8")

        with self.assertRaisesRegex(handoff.ManifestError, "exceeds"):
            handoff.bounded_load_manifest(oversized)

    def test_execute_handoff_serializes_complete_result(self) -> None:
        self.write_manifest(self.base_manifest())
        expected_output = self.root / "job-001-artifacts" / "semgrep-report.html"
        expected_output.parent.mkdir(parents=True, exist_ok=True)
        expected_output.write_text("<html></html>", encoding="utf-8")

        with patch.object(
            handoff,
            "_execute_project_job",
            return_value=(0, {"report": str(expected_output)}, ["manual warning"]),
        ):
            result = handoff.execute_handoff_manifest(self.manifest_path)

        self.assertEqual(result["status"], "complete")
        self.assertIn("manual warning", result["warnings"])
        self.assertEqual(result["outputPaths"]["report"], str(expected_output))
        result_file = Path(result["resultPath"])
        self.assertTrue(result_file.exists())
        persisted = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(persisted["schema"], handoff.RESULT_SCHEMA)
        self.assertEqual(persisted["status"], "complete")
        self.assertEqual(persisted["job"]["id"], "job-001")
        self.assertIn("startedAt", persisted)
        self.assertIn("finishedAt", persisted)
        self.assertEqual(
            persisted["provenance"]["manifest"]["path"], str(self.manifest_path.resolve())
        )

    def test_execute_handoff_marks_manual_only_jobs_as_unsupported(self) -> None:
        self.write_manifest(self.base_manifest(type="apk-creator"))

        result = handoff.execute_handoff_manifest(self.manifest_path)

        self.assertEqual(result["status"], "unsupported")
        self.assertTrue(
            any("unsupported" in warning.lower() for warning in result["warnings"])
        )


if __name__ == "__main__":
    unittest.main()

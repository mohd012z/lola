import tempfile
import unittest
from pathlib import Path

from lola_prospective_observer_coverage import audit_observer_coverage


class ProspectiveObserverCoverageTests(unittest.TestCase):
    def test_unwatched_production_workflow_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflows = Path(tmp)
            (workflows / "prospective-holdout-observer.yml").write_text(
                'name: Prospective holdout observer\n\n'
                'on:\n'
                '  workflow_run:\n'
                '    workflows: ["Existing Check"]\n'
                '    types: [completed]\n',
                encoding="utf-8",
            )
            (workflows / "existing.yml").write_text(
                "name: Existing Check\non: [push]\n", encoding="utf-8"
            )
            (workflows / "new-check.yml").write_text(
                "name: New Production Check\non: [push]\n", encoding="utf-8"
            )

            result = audit_observer_coverage(workflows)

            self.assertFalse(result["complete"])
            self.assertEqual(result["missing"], ["New Production Check"])
            self.assertEqual(result["extra"], [])

    def test_repository_workflow_coverage_is_complete(self):
        repo = Path(__file__).resolve().parents[1]
        result = audit_observer_coverage(repo / ".github" / "workflows")

        self.assertTrue(result["complete"], result)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["extra"], [])
        self.assertEqual(
            result["production_workflows"],
            [
                "LLM Guardrail CI",
                "Lola Bot Health",
                "Lola Code Doctor",
                "Toolchain smoke check",
            ],
        )

    def test_toolchain_tracks_and_compiles_coverage_checker(self):
        repo = Path(__file__).resolve().parents[1]
        toolchain = (repo / ".github" / "workflows" / "toolchain-check.yml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(toolchain.count('lola_prospective_observer_coverage.py'), 3)


if __name__ == "__main__":
    unittest.main()

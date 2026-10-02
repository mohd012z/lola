import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from lola import main
from lola_prospective_holdout import (
    ANCHOR_SHA,
    PREREGISTRATION_SEAL,
    build_selection_lock,
    validate_holdout_candidate,
)


class ProspectiveHoldoutLockTests(unittest.TestCase):
    def _candidate(self, failure_sha="1" * 40):
        return {
            "schema_version": "prospective-holdout-candidate-v1",
            "registration_id": "lola-preflight-validity-prospective-001",
            "preregistration_anchor_sha": ANCHOR_SHA,
            "preregistration_seal_sha256": PREREGISTRATION_SEAL,
            "failure_commit_sha": failure_sha,
            "observed_failure": {
                "surface": "workflow",
                "observable_failure": True,
                "naturally_occurring": True,
                "benchmark_authored": False,
                "intentionally_injected": False,
                "documentation_only": False,
                "test_only_fixture": False,
                "same_origin_training": False,
                "known_outcome_at_selection": False,
                "cherry_picked": False,
                "first_eligible_confirmed": True,
                "before_evidence_refs": ["ci:run-123"],
                "prior_post_anchor_failures_reviewed": [],
            },
        }

    def test_valid_candidate_builds_pre_repair_lock_only(self):
        candidate = self._candidate()
        verdict = validate_holdout_candidate(candidate, trust_ancestry_flag=True)
        self.assertTrue(verdict["valid_candidate"])

        lock = build_selection_lock(candidate, trust_ancestry_flag=True)
        self.assertEqual(lock["status"], "LOCKED_AWAITING_REPAIR")
        self.assertEqual(lock["phase"], "SELECTION_LOCK")
        self.assertEqual(lock["failure_commit_sha"], "1" * 40)
        self.assertEqual(lock["outcome_at_selection"], "UNKNOWN")
        self.assertIsNone(lock["fix_commit_sha"])
        self.assertIsNone(lock["result_commit_sha"])
        self.assertFalse(lock["prospective_claim"])
        self.assertFalse(lock["blind_holdout_claim"])
        self.assertFalse(lock["production_world_claim"])
        self.assertRegex(lock["selection_lock_digest_sha256"], r"^[0-9a-f]{64}$")

    def test_known_outcome_or_injected_failure_cannot_be_locked(self):
        candidate = self._candidate()
        candidate["observed_failure"]["known_outcome_at_selection"] = True
        candidate["observed_failure"]["intentionally_injected"] = True
        verdict = validate_holdout_candidate(candidate, trust_ancestry_flag=True)
        self.assertFalse(verdict["valid_candidate"])
        self.assertIn("outcome_known_at_selection", verdict["reasons"])
        self.assertIn("intentional_injection_forbidden", verdict["reasons"])
        with self.assertRaises(ValueError):
            build_selection_lock(candidate, trust_ancestry_flag=True)

    def test_before_evidence_and_first_eligible_confirmation_are_required(self):
        candidate = self._candidate()
        candidate["observed_failure"]["first_eligible_confirmed"] = False
        candidate["observed_failure"]["before_evidence_refs"] = []
        verdict = validate_holdout_candidate(candidate, trust_ancestry_flag=True)
        self.assertFalse(verdict["valid_candidate"])
        self.assertIn("first_eligible_not_confirmed", verdict["reasons"])
        self.assertIn("before_evidence_missing", verdict["reasons"])

    def test_real_git_ancestry_requires_failure_after_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "LOLA Test"], check=True)
            for label in ("anchor", "failure"):
                (repo / "state.txt").write_text(label, encoding="utf-8")
                subprocess.run(["git", "-C", str(repo), "add", "state.txt"], check=True)
                subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", label], check=True)
                if label == "anchor":
                    anchor = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
                else:
                    failure = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

            candidate = self._candidate(failure)
            candidate["preregistration_anchor_sha"] = anchor
            verdict = validate_holdout_candidate(
                candidate,
                repository_root=repo,
                expected_anchor_sha=anchor,
            )
            self.assertTrue(verdict["git_ancestry_verified"])
            self.assertTrue(verdict["valid_candidate"])

            candidate["failure_commit_sha"] = anchor
            verdict = validate_holdout_candidate(
                candidate,
                repository_root=repo,
                expected_anchor_sha=anchor,
            )
            self.assertFalse(verdict["valid_candidate"])
            self.assertIn("failure_not_after_anchor", verdict["reasons"])

    def test_cli_rejects_candidate_without_real_ancestry_and_writes_no_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            candidate_path = tmpdir / "candidate.json"
            output_path = tmpdir / "selection-lock.json"
            candidate_path.write_text(json.dumps(self._candidate()), encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(
                sys,
                "argv",
                [
                    "lola.py",
                    "--prospective-holdout-lock",
                    str(candidate_path),
                    "--holdout-lock-output",
                    str(output_path),
                ],
            ):
                with redirect_stdout(stdout):
                    rc = main()

        self.assertEqual(rc, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["valid_candidate"])
        self.assertIn("failure_not_after_anchor", payload["reasons"])
        self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from lola import main
from lola_tiny_beast_benchmark import (
    BenchmarkTrial,
    evaluate_growth,
    load_benchmark_pair,
    run_tiny_beast_smoke,
)


class TinyBeastBenchmarkTests(unittest.TestCase):
    def _passing_payload(self):
        return {
            "baseline": {
                "task_id": "p0", "family": "dependency-debug", "transfer_distance": 0,
                "model_id": "tiny-a", "hardware_id": "cpu-a", "verified": True,
                "false_solved": False, "intellectual_level": 4, "actions": 10,
                "escalations": 2, "tokens": 5000, "wall_time_ms": 8000,
                "external_ai_used": False, "regression_failures": 0,
            },
            "learned": {
                "task_id": "p2", "family": "dependency-debug", "transfer_distance": 2,
                "model_id": "tiny-a", "hardware_id": "cpu-a", "verified": True,
                "false_solved": False, "intellectual_level": 1, "actions": 3,
                "escalations": 0, "tokens": 1200, "wall_time_ms": 2500,
                "external_ai_used": False, "regression_failures": 0,
            },
        }

    def test_verified_unseen_downshift_passes(self):
        before = BenchmarkTrial(
            task_id="p0",
            family="dependency-debug",
            transfer_distance=0,
            model_id="tiny-local-v1",
            hardware_id="cpu-a",
            verified=True,
            false_solved=False,
            intellectual_level=4,
            actions=18,
            escalations=2,
            tokens=10000,
            wall_time_ms=12000,
            external_ai_used=False,
            regression_failures=0,
        )
        after = BenchmarkTrial(
            task_id="p2",
            family="dependency-debug",
            transfer_distance=2,
            model_id="tiny-local-v1",
            hardware_id="cpu-a",
            verified=True,
            false_solved=False,
            intellectual_level=1,
            actions=4,
            escalations=0,
            tokens=1800,
            wall_time_ms=3500,
            external_ai_used=False,
            regression_failures=0,
        )
        result = evaluate_growth(before, after)
        self.assertTrue(result.passed)
        self.assertEqual(result.status, "SYSTEM_INTELLIGENCE_GAIN")
        self.assertEqual(result.intellectual_downshift, 3)
        self.assertEqual(result.action_delta, -14)
        self.assertEqual(result.escalation_delta, -2)
        self.assertEqual(result.token_delta, -8200)

    def test_changed_model_rejects_architecture_gain_claim(self):
        before = BenchmarkTrial(
            task_id="p0", family="x", transfer_distance=0,
            model_id="tiny-a", hardware_id="cpu-a", verified=True,
            intellectual_level=4, actions=10,
        )
        after = BenchmarkTrial(
            task_id="p2", family="x", transfer_distance=2,
            model_id="large-b", hardware_id="cpu-a", verified=True,
            intellectual_level=1, actions=3,
        )
        result = evaluate_growth(before, after)
        self.assertFalse(result.passed)
        self.assertIn("model_changed", result.reasons)

    def test_t1_repeat_is_not_enough_for_beast_claim(self):
        before = BenchmarkTrial(
            task_id="p0", family="x", transfer_distance=0,
            model_id="tiny-a", hardware_id="cpu-a", verified=True,
            intellectual_level=4, actions=10,
        )
        after = BenchmarkTrial(
            task_id="p1", family="x", transfer_distance=1,
            model_id="tiny-a", hardware_id="cpu-a", verified=True,
            intellectual_level=1, actions=3,
        )
        result = evaluate_growth(before, after)
        self.assertFalse(result.passed)
        self.assertIn("transfer_distance_below_t2", result.reasons)

    def test_false_solved_or_regression_blocks_pass(self):
        before = BenchmarkTrial(
            task_id="p0", family="x", transfer_distance=0,
            model_id="tiny-a", hardware_id="cpu-a", verified=True,
            intellectual_level=4, actions=10,
        )
        after = BenchmarkTrial(
            task_id="p2", family="x", transfer_distance=2,
            model_id="tiny-a", hardware_id="cpu-a", verified=True,
            false_solved=True, regression_failures=1,
            intellectual_level=1, actions=3,
        )
        result = evaluate_growth(before, after)
        self.assertFalse(result.passed)
        self.assertIn("false_solved", result.reasons)
        self.assertIn("regression_failure", result.reasons)

    def test_sovereign_claim_requires_no_external_ai_after_learning(self):
        before = BenchmarkTrial(
            task_id="p0", family="x", transfer_distance=0,
            model_id="tiny-a", hardware_id="cpu-a", verified=True,
            intellectual_level=4, actions=10,
        )
        after = BenchmarkTrial(
            task_id="p2", family="x", transfer_distance=2,
            model_id="tiny-a", hardware_id="cpu-a", verified=True,
            intellectual_level=1, actions=3, external_ai_used=True,
        )
        result = evaluate_growth(before, after, require_sovereign=True)
        self.assertFalse(result.passed)
        self.assertIn("external_ai_used", result.reasons)

    def test_json_pair_loader_is_strict(self):
        payload = self._passing_payload()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pair.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            before, after = load_benchmark_pair(path)
        self.assertEqual(before.task_id, "p0")
        self.assertEqual(after.task_id, "p2")

    def test_builtin_smoke_is_a_harness_test_not_a_real_beast_claim(self):
        result = run_tiny_beast_smoke()
        self.assertTrue(result["passed"])
        self.assertEqual(result["mode"], "HARNESS-SMOKE")
        self.assertFalse(result["empirical_beast_claim"])
        self.assertEqual(result["status"], "SYSTEM_INTELLIGENCE_GAIN")

    def test_cli_tiny_beast_smoke_runs_without_target(self):
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["lola.py", "--tiny-beast-smoke"]):
            with redirect_stdout(stdout):
                rc = main()
        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["passed"])
        self.assertFalse(payload["empirical_beast_claim"])

    def test_cli_empirical_benchmark_can_prove_sovereign_gain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pair.json"
            path.write_text(json.dumps(self._passing_payload()), encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(
                sys,
                "argv",
                ["lola.py", "--tiny-beast-benchmark", str(path), "--require-sovereign"],
            ):
                with redirect_stdout(stdout):
                    rc = main()
        self.assertEqual(rc, 0)
        result = json.loads(stdout.getvalue())
        self.assertTrue(result["passed"])
        self.assertTrue(result["empirical_beast_claim"])
        self.assertTrue(result["sovereign"])

    def test_cli_empirical_benchmark_returns_nonzero_when_not_proven(self):
        payload = self._passing_payload()
        payload["learned"]["model_id"] = "larger-model"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pair.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(sys, "argv", ["lola.py", "--tiny-beast-benchmark", str(path)]):
                with redirect_stdout(stdout):
                    rc = main()
        self.assertEqual(rc, 2)
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["passed"])
        self.assertFalse(result["empirical_beast_claim"])
        self.assertIn("model_changed", result["reasons"])


if __name__ == "__main__":
    unittest.main()
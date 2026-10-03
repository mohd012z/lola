import unittest

from lola_delta_observe import PredictionErrorStore, run_recheck


class DeltaObserveTests(unittest.TestCase):
    def test_fresh_store_predicts_zero(self):
        s = PredictionErrorStore()
        self.assertAlmostEqual(s.prediction, 0.0)

    def test_observe_stores_prediction_error(self):
        s = PredictionErrorStore()
        out = s.observe(8192)
        # fresh store predicted 0, observed 8192 -> error 8192
        self.assertAlmostEqual(out["prediction_error"], 8192.0)
        # the forecast converges toward the observed value
        self.assertGreater(out["converged"], 0.0)
        self.assertLess(out["converged"], 8192.0)
        self.assertEqual(out["step"], 1)

    def test_second_observe_error_is_gap_not_full(self):
        # the delta rule's property: overwrite CORRECTS, doesn't duplicate.
        # After the first observe the forecast is non-zero, so the second
        # (same) observation has a SMALLER error than the first.
        s = PredictionErrorStore()
        first = s.observe(8192)
        second = s.observe(8192)
        self.assertLess(second["prediction_error"], first["prediction_error"])
        # forecast keeps converging toward 8192
        self.assertGreater(second["converged"], first["converged"])

    def test_snapshot_replay_roundtrip(self):
        s = PredictionErrorStore()
        s.observe(100)
        s.observe(120)
        snap = s.snapshot()
        s2 = PredictionErrorStore.from_snapshot(snap)
        self.assertAlmostEqual(s2.prediction, s.prediction)
        out = s2.observe(130)
        self.assertAlmostEqual(out["prediction_error"],
                               130 - s.prediction)

    def test_run_recheck_sequence(self):
        res = run_recheck(PredictionErrorStore(), [100, 100, 100])
        self.assertEqual(len(res["cycles"]), 3)
        # first cycle error is the full 100; last is near-zero
        self.assertAlmostEqual(res["cycles"][0]["prediction_error"], 100.0)
        self.assertLess(abs(res["cycles"][-1]["prediction_error"]),
                        abs(res["cycles"][0]["prediction_error"]))
        # converged prediction approaches the stable value
        self.assertGreater(res["converged_prediction"], 0.0)
        self.assertIn("total_abs_error", res)
        self.assertIn("snapshot", res)

    def test_deterministic(self):
        a = run_recheck(PredictionErrorStore(), [50, 60, 70])
        b = run_recheck(PredictionErrorStore(), [50, 60, 70])
        self.assertEqual(a["converged_prediction"], b["converged_prediction"])
        self.assertEqual(a["total_abs_error"], b["total_abs_error"])

    def test_forecast_converges_on_stable_signal(self):
        # the observe-stage contract: repeated observations of a stable
        # quantity drive the prediction error to ~0 (the forecast tracks it).
        res = run_recheck(PredictionErrorStore(), [8192] * 20)
        # late-cycle errors are tiny compared to the first
        self.assertLess(abs(res["cycles"][-1]["prediction_error"]), 1.0)
        self.assertGreater(res["converged_prediction"], 8190.0)
        self.assertLess(res["converged_prediction"], 8193.0)


class LoopDeltaIntegrationTests(unittest.TestCase):
    def test_observed_sequence_attaches_delta_store(self):
        from lola_cognitive_loop import run_cognitive_loop
        out = run_cognitive_loop({
            "question": "what is the decoder buffer size",
            "verified_state": {"decoder buffer size": "8192 bytes"},
            "observed_sequence": [8192, 8192, 8192],
        })
        self.assertIn("delta_store", out)
        self.assertEqual(len(out["delta_store"]["cycles"]), 3)
        self.assertIn("converged_prediction", out["delta_store"])

    def test_no_sequence_no_delta_store(self):
        from lola_cognitive_loop import run_cognitive_loop
        out = run_cognitive_loop({
            "question": "what is the decoder buffer size",
            "verified_state": {"decoder buffer size": "8192 bytes"},
        })
        self.assertNotIn("delta_store", out)


class StackVerifyTests(unittest.TestCase):
    def test_verify_all_modules_import_and_stages_pass(self):
        from lola_stack_verify import verify_merged_stack
        res = verify_merged_stack()
        self.assertTrue(res["passed"], res)
        # every New LOLA module imports cleanly
        for mod in ("lola_delta_memory", "lola_interaction_gateway",
                    "lola_novelty", "lola_cognition_ladder",
                    "lola_learning_gate", "lola_radar_scan",
                    "lola_parallelism_planner", "lola_cognitive_budget",
                    "lola_presentation", "lola_fast_triage",
                    "lola_research_stages", "lola_evidence_bus",
                    "lola_runtime_loop", "lola_answer_planner",
                    "lola_agent_roles", "lola_observe",
                    "lola_recheck", "lola_cognitive_loop",
                    "lola_cognitive_entry", "lola_full_chain_smoke",
                    "lola_delta_observe"):
            self.assertTrue(res["modules"][mod],
                            f"import failed: {mod}")
        # the full-chain smoke stage passed
        self.assertTrue(res["stages"]["full_chain_smoke"])
        # the delta-observe stage passed
        self.assertTrue(res["stages"]["delta_observe"])

    def test_cli_stack_verify(self):
        import json
        import subprocess
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [sys.executable, "lola.py", "--stack-verify"],
            capture_output=True, text=True, cwd=repo_root,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["passed"])


if __name__ == "__main__":
    unittest.main()

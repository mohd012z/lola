import json
import unittest

from lola_cognitive_loop import run_cognitive_loop
from lola_recheck import recheck_cycle


class RecheckCycleTests(unittest.TestCase):
    def test_clean_cycle_continues(self):
        r = recheck_cycle(expected_values=(5,), observed_values=(5,))
        self.assertFalse(r.needs_recheck)
        self.assertTrue(r.continued)
        self.assertIsNone(r.root_cause_gap)
        self.assertEqual(r.prediction_error, 0.0)

    def test_large_error_stops_before_answer(self):
        r = recheck_cycle(expected_values=(5,), observed_values=(8,))
        self.assertTrue(r.needs_recheck)
        self.assertFalse(r.continued)
        self.assertIsNotNone(r.root_cause_gap)
        self.assertAlmostEqual(r.prediction_error, 3.0)

    def test_multiple_cycles_stops_at_first_bad(self):
        # cycle 0 clean, cycle 1 off -> stops at cycle 1
        r = recheck_cycle(expected_values=(5, 10),
                          observed_values=(5, 13))
        self.assertFalse(r.continued)
        self.assertEqual(len(r.cycles), 2)
        self.assertTrue(r.cycles[1]["needs_recheck"])
        self.assertFalse(r.cycles[0]["needs_recheck"])

    def test_tolerance_boundary(self):
        # exactly at tolerance is NOT a recheck (strictly greater)
        r = recheck_cycle(expected_values=(5,), observed_values=(6,),
                          tolerance=1.0)
        self.assertFalse(r.needs_recheck)
        r2 = recheck_cycle(expected_values=(5,), observed_values=(6.1,),
                           tolerance=1.0)
        self.assertTrue(r2.needs_recheck)

    def test_mismatched_lengths_rejected(self):
        with self.assertRaises(ValueError):
            recheck_cycle(expected_values=(5,), observed_values=(5, 6))

    def test_deterministic(self):
        a = recheck_cycle((5, 10), (5, 13))
        b = recheck_cycle((5, 10), (5, 13))
        self.assertEqual(a.cycles, b.cycles)
        self.assertEqual(a.root_cause_gap, b.root_cause_gap)


class CognitiveLoopRunnerTests(unittest.TestCase):
    def test_answer_path_full_output(self):
        out = run_cognitive_loop({
            "question": "what is the decoder buffer size",
            "verified_state": {"decoder buffer size": "8192 bytes"},
        })
        # report fields present
        self.assertEqual(out["report"]["route"], "ANSWER")
        # "what is the decoder buffer size" carries no troubleshooting
        # keyword -> GENERIC (deterministic classification)
        self.assertEqual(out["report"]["answer_type"], "GENERIC")
        self.assertIn("Summary", out["report"]["planned_sections"])
        # roles derived from the question
        self.assertIn("EXPLORER", out["roles"])
        self.assertIn("VERIFIER", out["roles"])
        # /flow output renders
        self.assertIn("Intake", out["flow"])
        # governor present
        self.assertIn(out["governor"], ("PROMOTE", "RETAIN", "REJECT"))
        # no recheck without observation
        self.assertIsNone(out["report"]["prediction_error"])
        self.assertFalse(out["report"]["needs_recheck"])
        self.assertIsNone(out.get("recheck"))

    def test_recheck_edge_named_when_delta_large(self):
        out = run_cognitive_loop({
            "question": "what is the decoder buffer size",
            "verified_state": {"decoder buffer size": "8192 bytes"},
            "prediction": 100,
            "observed": 8192,
        })
        self.assertTrue(out["report"]["needs_recheck"])
        self.assertIsNotNone(out["recheck"])
        self.assertIn("prediction error", out["recheck"]["root_cause_gap"])
        self.assertFalse(out["recheck"]["continued"])

    def test_json_serializable(self):
        out = run_cognitive_loop({
            "question": "research the options",
            "inventory": {"known": [], "unknown": ["a", "b"]},
        })
        # must round-trip through JSON without error
        s = json.dumps(out, sort_keys=True)
        self.assertIsInstance(json.loads(s), dict)

    def test_quarantine_surfaced(self):
        out = run_cognitive_loop({
            "question": "why does it freeze",
            "frozen_idea": {"frozen_before_external": False},
            "external_hits": ["study says X"],
        })
        self.assertTrue(out["report"]["quarantined"])
        self.assertIn("NOVELTY_BEFORE_EXTERNAL", out["report"]["violations"])
        self.assertEqual(out["governor"], "REJECT")


class CliLoopRunnerTest(unittest.TestCase):
    def test_cli_flag_runs_and_passes(self):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        input_doc = {"question": "what is the decoder buffer size",
                     "verified_state": {"decoder buffer size": "8192 bytes"}}
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as f:
            json.dump(input_doc, f)
            path = f.name
        proc = subprocess.run(
            [sys.executable, "lola.py", "--cognitive-loop", path],
            capture_output=True, text=True, cwd=repo_root,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["report"]["route"], "ANSWER")


if __name__ == "__main__":
    unittest.main()

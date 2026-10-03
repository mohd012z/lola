import unittest

from lola_answer_planner import plan_answer, planned_sections
from lola_cognitive_loop_smoke import run_cognitive_loop_smoke


class AnswerPlannerTests(unittest.TestCase):
    def test_troubleshooting(self):
        p = plan_answer("why does the application freeze after ten seconds")
        self.assertEqual(p.question_type, "TROUBLESHOOTING")
        self.assertEqual(p.sections[:3],
                         ("Finding", "Evidence", "Root cause"))
        self.assertIn("Unknowns", p.sections)

    def test_research(self):
        p = plan_answer("research and compare the evidence for scheduling options")
        self.assertEqual(p.question_type, "RESEARCH")
        self.assertIn("Competing explanations", p.sections)
        self.assertIn("Conclusion", p.sections)
        self.assertNotIn("Root cause", p.sections)

    def test_implementation(self):
        p = plan_answer("implement the new build pipeline and deploy it")
        self.assertEqual(p.question_type, "IMPLEMENTATION")
        self.assertIn("Dependencies", p.sections)
        self.assertIn("Regression", p.sections)

    def test_generic(self):
        p = plan_answer("hello")
        self.assertEqual(p.question_type, "GENERIC")
        self.assertIn("Summary", p.sections)

    def test_deterministic(self):
        a = plan_answer("why does it fail")
        b = plan_answer("why does it fail")
        self.assertEqual(a.sections, b.sections)
        self.assertEqual(a.question_type, b.question_type)

    def test_batch_convenience(self):
        out = planned_sections([
            "why does it crash",
            "research the options",
            "implement the change",
            "hi",
        ])
        self.assertEqual(len(out), 4)
        self.assertIn("Root cause", out[0])
        self.assertIn("Conclusion", out[1])
        self.assertIn("Dependencies", out[2])
        self.assertIn("Summary", out[3])


class LoopPlannerIntegrationTests(unittest.TestCase):
    def test_report_carries_plan(self):
        from lola_runtime_loop import run_loop
        r = run_loop("why does the build fail",
                     verified_state={"build fail": "missing dependency"},
                     inspectable=())
        # answer route still works; plan present
        self.assertTrue(hasattr(r, "answer_type"))
        self.assertTrue(hasattr(r, "planned_sections"))
        self.assertEqual(r.answer_type, "TROUBLESHOOTING")

    def test_trace_shows_answer_type(self):
        from lola_runtime_loop import run_loop
        r = run_loop("why does the build fail",
                     verified_state={"build fail": "missing dependency"},
                     inspectable=())
        steps = [t["step"] for t in r.trace]
        self.assertTrue(any(s.startswith("Answer") for s in steps))


class CognitiveLoopSmokeTests(unittest.TestCase):
    def test_smoke_passes_end_to_end(self):
        result = run_cognitive_loop_smoke()
        self.assertTrue(result["passed"],
                        f"smoke failed: {[c for c in result['checks'] if not c['ok']]}")
        # every check present and green
        names = {c["name"] for c in result["checks"]}
        for required in ("triage_answer_route", "triage_map_route",
                         "radar_pass_b_selective", "clean_freeze_allows_research",
                         "unfrozen_external_quarantined",
                         "planner_troubleshooting", "planner_research",
                         "planner_implementation", "planner_generic",
                         "flow_trace_renders", "governor_promote_verified",
                         "agent_count_does_not_vote"):
            self.assertIn(required, names)
        self.assertTrue(all(c["ok"] for c in result["checks"]))
        # deterministic
        r2 = run_cognitive_loop_smoke()
        self.assertEqual(result["checks"], r2["checks"])


class CliSmokeTest(unittest.TestCase):
    def test_cli_flag_runs_and_passes(self):
        import subprocess
        import sys
        proc = subprocess.run(
            [sys.executable, "lola.py", "--cognitive-loop-smoke"],
            capture_output=True, text=True, cwd="/opt/data/lola",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        import json
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["passed"])


if __name__ == "__main__":
    unittest.main()

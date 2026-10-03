import unittest

from lola_cognitive_budget import CognitiveBudget, stop_condition
from lola_parallelism_planner import plan_parallelism
from lola_presentation import (
    STYLES, Answer, Section, apply_style, confidence_from_evidence,
    render_flow,
)
from lola_radar_scan import RADAR_DIMENSIONS, fast_radar, pass_b


class RadarTests(unittest.TestCase):
    def test_dimensions_cover_core_360(self):
        names = {name for name, _ in RADAR_DIMENSIONS}
        for required in ("architecture", "code", "runtime", "security",
                         "network", "storage", "tests", "performance"):
            self.assertIn(required, names)

    def test_relevance_tiers(self):
        r = fast_radar("why does the decoder hang in runtime performance")
        by = {d.name: d for d in r.dimensions}
        self.assertEqual(by["runtime"].relevance, "ACTIVE")
        self.assertEqual(by["code"].relevance, "REVIEW")
        self.assertEqual(by["storage"].relevance, "LOW")

    def test_status_assignment(self):
        r = fast_radar("python runtime decoder",
                       known=("runtime",), uncertain=("storage",),
                       contradictions=("network",))
        by = {d.name: d for d in r.dimensions}
        self.assertEqual(by["runtime"].status, "GREEN")
        self.assertEqual(by["storage"].status, "YELLOW")
        self.assertEqual(by["network"].status, "RED")
        self.assertEqual(by["architecture"].status, "GREY")

    def test_pass_b_selective(self):
        r = fast_radar("python runtime decoder",
                       known=("runtime",), uncertain=("storage",),
                       contradictions=("network",))
        pb = pass_b(r)
        self.assertIn("storage", pb)
        self.assertIn("network", pb)
        self.assertNotIn("runtime", pb)   # GREEN — understood
        self.assertNotIn("architecture", pb)  # GREY — irrelevant

    def test_flagged_dimension_studied_even_if_low_relevance(self):
        # an explicitly uncertain dimension is investigated even when the
        # question never used its keywords — the flag beats the cheap score
        r = fast_radar("python decoder", uncertain=("storage",))
        pb = pass_b(r)
        self.assertIn("storage", pb)

    def test_irrelevant_low_dimension_skipped(self):
        # nothing flagged, no keywords -> GREY -> never investigated
        r = fast_radar("python decoder")
        pb = pass_b(r)
        self.assertNotIn("build", pb)
        self.assertNotIn("ui", pb)


class ParallelismTests(unittest.TestCase):
    def test_independent_nodes_same_wave(self):
        p = plan_parallelism(nodes=("A", "B", "C"), edges=())
        self.assertEqual(len(p.waves), 1)
        self.assertEqual(sorted(p.waves[0]), ["A", "B", "C"])
        self.assertTrue(p.is_parallel)

    def test_dependency_chains_sequential(self):
        p = plan_parallelism(nodes=("A", "D", "E"),
                             edges=(("A", "D"), ("D", "E")))
        self.assertEqual(len(p.waves), 3)
        self.assertEqual([list(w) for w in p.waves], [["A"], ["D"], ["E"]])
        self.assertFalse(p.is_parallel)

    def test_mixed_graph(self):
        p = plan_parallelism(nodes=("A", "B", "C", "D", "E", "F"),
                             edges=(("A", "D"), ("B", "D"), ("D", "E")))
        self.assertEqual(sorted(p.waves[0]), ["A", "B", "C", "F"])
        self.assertEqual(p.waves[1], ["D"])
        self.assertEqual(p.waves[2], ["E"])
        self.assertTrue(p.is_parallel)

    def test_cycle_fails_closed(self):
        with self.assertRaises(ValueError):
            plan_parallelism(nodes=("A", "B"),
                             edges=(("A", "B"), ("B", "A")))


class BudgetStopTests(unittest.TestCase):
    def test_answered_stops_first(self):
        st = {"answered": True, "evidence": ["e1"], "budget": CognitiveBudget(),
              "human_required": True}
        self.assertEqual(stop_condition(st), "ANSWERED_WITH_EVIDENCE")

    def test_ordering(self):
        b = CognitiveBudget(tokens=10)
        st = {"answered": False, "uncertainty_changes_decision": True,
              "info_gain": 0.05, "budget": b, "evidence_available": False,
              "human_required": True}
        self.assertEqual(stop_condition(st), "LOW_INFORMATION_GAIN")

    def test_budget_reached_stops(self):
        b = CognitiveBudget(tokens=10)
        b.consume("tokens", 10)
        st = {"answered": False, "uncertainty_changes_decision": True,
              "info_gain": 0.9, "budget": b, "evidence_available": True,
              "human_required": False}
        self.assertEqual(stop_condition(st), "BUDGET_REACHED")

    def test_none_continues(self):
        b = CognitiveBudget()
        st = {"answered": False, "uncertainty_changes_decision": True,
              "info_gain": 0.8, "budget": b, "evidence_available": True,
              "human_required": False}
        self.assertIsNone(stop_condition(st))

    def test_budget_tracks_each_axis(self):
        b = CognitiveBudget(tokens=100, agents=4)
        b.consume("tokens", 40)
        b.consume("agents", 4)
        self.assertTrue(b.used["tokens"] == 40)
        self.assertTrue(b.exhausted("agents"))
        self.assertFalse(b.exhausted("tokens"))


class PresentationTests(unittest.TestCase):
    def _answer(self):
        return Answer(sections=(
            Section("Finding", "The root cause is the decoder buffer", required=True),
            Section("Evidence", "obs-1, obs-2", required=True),
            Section("Root cause", "lifecycle timing", required=True),
            Section("Fix", "increase buffer to 8k", required=True),
            Section("Verification", "repro passes", required=True),
            Section("Unknowns", "none identified", required=True),
            Section("Appendix", "long optional detail " * 20, required=False),
        ))

    def test_all_styles_preserve_required(self):
        base = self._answer()
        req_titles = [s.title for s in base.sections if s.required]
        for style in STYLES:
            out = apply_style(base, style)
            self.assertEqual([s.title for s in out.sections if s.required],
                             req_titles, style)

    def test_compact_drops_optional(self):
        out = apply_style(self._answer(), "COMPACT")
        titles = {s.title for s in out.sections}
        self.assertNotIn("Appendix", titles)

    def test_beginner_plain_lead(self):
        out = apply_style(self._answer(), "BEGINNER")
        self.assertTrue(out.lead, "BEGINNER must add a plain-language lead")
        self.assertIn("decoder buffer", out.lead.lower())

    def test_style_never_reorders_required(self):
        base = self._answer()
        req = [s.title for s in base.sections if s.required]
        for style in STYLES:
            out = apply_style(base, style)
            self.assertEqual([s.title for s in out.sections if s.required], req, style)

    def test_confidence_no_percentage(self):
        claims = [
            {"id": "c1", "evidence_ids": ["e1"], "state": "SUPPORTED"},
            {"id": "c2", "evidence_ids": [], "state": "UNVERIFIED"},
        ]
        out = confidence_from_evidence(claims)
        self.assertIsInstance(out["confidence"], str)
        self.assertNotIn("%", out["confidence"])
        self.assertEqual(out["confidence"], "PARTIALLY_SUPPORTED")
        self.assertIn("e1", out["evidence_ids"])

    def test_confidence_contradicted_wins(self):
        claims = [
            {"id": "c1", "evidence_ids": ["e1"], "state": "SUPPORTED"},
            {"id": "c2", "evidence_ids": ["e2"], "state": "CONTRADICTED"},
        ]
        out = confidence_from_evidence(claims)
        self.assertEqual(out["confidence"], "CONTRADICTED")

    def test_confidence_all_supported(self):
        claims = [
            {"id": "c1", "evidence_ids": ["e1"], "state": "SUPPORTED"},
        ]
        out = confidence_from_evidence(claims)
        self.assertEqual(out["confidence"], "SUPPORTED")

    def test_render_flow_safe_trace(self):
        trace = [
            {"step": "Intake", "status": "done"},
            {"step": "Local knowledge checked", "status": "done"},
            {"step": "Researching remaining 2", "status": "in-progress"},
            {"step": "Verification", "status": "pending"},
        ]
        out = render_flow(trace, task_id="481", external_ai_used=False,
                          evidence_count=14,
                          current_uncertainty="decoder scheduling vs lifecycle timing")
        self.assertIn("TASK #481", out)
        self.assertIn("Intake", out)
        self.assertIn("External AI:", out)
        self.assertIn("not used yet", out)
        self.assertIn("14 observations", out)
        self.assertIn("decoder scheduling", out)
        # markers
        self.assertIn("✓", out)
        self.assertIn("●", out)
        self.assertIn("○", out)


if __name__ == "__main__":
    unittest.main()

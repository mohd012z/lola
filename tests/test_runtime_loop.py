import unittest

from lola_evidence_bus import EvidenceBus, Finding
from lola_fast_triage import fast_triage
from lola_research_stages import source_rank, build_research_plan
from lola_runtime_loop import run_loop, learning_governor


class TriageTests(unittest.TestCase):
    def test_answer_from_verified_first(self):
        t = fast_triage(
            "what is the decoder buffer size",
            verified_state={"decoder buffer size": "8192 bytes"},
            inspectable=("logs",),
        )
        self.assertEqual(t.route, "ANSWER")
        self.assertFalse(t.external_justified)
        self.assertIn("verified", t.why)
    def test_deterministic_inspection_second(self):
        t = fast_triage(
            "why does the build fail",
            verified_state={},
            inspectable=("build.log",),
        )
        self.assertEqual(t.route, "INSPECT")
        self.assertFalse(t.external_justified)

    def test_complexity_map_third(self):
        t = fast_triage(
            "why does the application freeze only on android sixteen",
            verified_state={},
            inspectable=(),
        )
        self.assertEqual(t.route, "MAP")
        self.assertFalse(t.external_justified)

    def test_no_route_is_external(self):
        # even MAP does not justify external on its own — the research
        # gate does that later, only if internal reasoning is exhausted
        t = fast_triage("something novel", verified_state={}, inspectable=())
        self.assertFalse(t.external_justified)


class ResearchPlanTests(unittest.TestCase):
    def test_source_hierarchy_order(self):
        self.assertLess(source_rank("code"), source_rank("analysis"))
        self.assertLess(source_rank("analysis"), source_rank("community"))
        self.assertLess(source_rank("community"), source_rank("ai"))

    def test_plan_requires_local_first_stages(self):
        p = build_research_plan(
            gap="decoder scheduling vs lifecycle timing",
            local_known=("decoder runs on main thread",),
            local_unknown=("android 16 lifecycle change",),
        )
        # staged order: local knowledge BEFORE any external source
        self.assertLess(p.stages.index("local_knowledge"),
                        p.stages.index("source_selection"))
        self.assertLess(p.stages.index("evidence_inventory"),
                        p.stages.index("internal_hypotheses"))
        self.assertIn("freeze_hypotheses", p.stages)

    def test_unfrozen_idea_cannot_research(self):
        with self.assertRaises(ValueError):
            build_research_plan(
                gap="g", local_known=(), local_unknown=(), frozen=False
            )

    def test_query_tree_grows_from_gaps(self):
        p = build_research_plan(
            gap="lifecycle timing on android 16",
            local_known=("lifecycle order in android 15",),
            local_unknown=("what changed in android 16",),
            external_gaps=("android 16 lifecycle change", "process start ordering"),
        )
        # root + one child per gap; children reference their parent
        self.assertGreaterEqual(len(p.queries), 3)
        self.assertTrue(all(q.root == "lifecycle timing on android 16" for q in p.queries))

    def test_source_class_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            build_research_plan(
                gap="g", local_known=("k",), local_unknown=("u",),
                sources=[("qwen", "community")],  # qwen is AI, not community
            )

    def test_ai_agreement_counts_zero_evidence(self):
        p = build_research_plan(
            gap="g", local_known=("k",), local_unknown=("u",),
            ai_agreement=("qwen", "gpt", "claude"),
        )
        self.assertEqual(p.evidence_contributions_from_ai, 0)
        self.assertEqual(len(p.ai_consulted), 3)


class EvidenceBusTests(unittest.TestCase):
    def test_findings_compressed_schema(self):
        bus = EvidenceBus()
        bus.register_evidence("e1")
        f = Finding(agent="A", finding="X", evidence_ids=("e1",),
                    unknowns=(), contradictions=(), next_gap="none")
        bus.submit(f)
        self.assertEqual(len(bus.findings), 1)

    def test_unknown_evidence_id_rejected(self):
        bus = EvidenceBus()
        bus.register_evidence("e1")
        with self.assertRaises(ValueError):
            bus.submit(Finding(agent="A", finding="X", evidence_ids=("eX",),
                               unknowns=(), contradictions=(), next_gap=""))

    def test_no_discrimination_no_winner(self):
        bus = EvidenceBus()
        bus.register_evidence("e1")
        bus.submit(Finding(agent="A", finding="X", evidence_ids=("e1",),
                           unknowns=(), contradictions=(), next_gap=""))
        bus.submit(Finding(agent="B", finding="X", evidence_ids=("e1",),
                           unknowns=(), contradictions=(), next_gap=""))
        winner, discriminating, note = bus.verdict("X", "Y")
        self.assertIsNone(winner)
        self.assertFalse(discriminating)

    def test_contradiction_picks_winner(self):
        bus = EvidenceBus()
        bus.register_evidence("e1", "e2")
        # X's own finding reports e2 as contradicting X; Y is clean
        bus.submit(Finding(agent="A", finding="X", evidence_ids=("e1",),
                           unknowns=(), contradictions=("e2",), next_gap=""))
        bus.submit(Finding(agent="B", finding="Y", evidence_ids=("e2",),
                           unknowns=(), contradictions=(), next_gap=""))
        winner, discriminating, note = bus.verdict("X", "Y")
        self.assertEqual(winner, "Y")
        self.assertTrue(discriminating)

    def test_agent_count_does_not_vote(self):
        # 2 agents for X (same evidence) vs 1 for Y whose own evidence
        # is contradicted by e1... Y still does NOT win: self-contradiction
        # is reported by the claim's OWN worker. Here X's workers are
        # clean; Y's worker reports e1 contradicts Y -> X wins by evidence,
        # even though it also won the vote (2 vs 1) — the point is the
        # decision path is the contradiction, not the count.
        bus = EvidenceBus()
        bus.register_evidence("e1", "e2")
        bus.submit(Finding(agent="A", finding="X", evidence_ids=("e1",),
                           unknowns=(), contradictions=(), next_gap=""))
        bus.submit(Finding(agent="C", finding="X", evidence_ids=("e1",),
                           unknowns=(), contradictions=(), next_gap=""))
        bus.submit(Finding(agent="B", finding="Y", evidence_ids=("e2",),
                           unknowns=(), contradictions=("e1",), next_gap=""))
        winner, _, _ = bus.verdict("X", "Y")
        self.assertEqual(winner, "X")


class RuntimeLoopTests(unittest.TestCase):
    def _base(self, **kw):
        base = dict(
            verified_state={"decoder buffer size": "8192 bytes"},
            inspectable=(),
            inventory={"known": (), "unknown": ("lifecycle timing",)},
            frozen_idea=None,
            external_hits=(),
        )
        base.update(kw)
        return base

    def test_answer_path_stops_early(self):
        r = run_loop("what is the decoder buffer size", **self._base())
        self.assertEqual(r.stopped_by, "ANSWERED_WITH_EVIDENCE")
        self.assertEqual(r.route, "ANSWER")
        self.assertEqual(r.agents_used, 0)
        self.assertEqual(r.external_sources_used, 0)
        self.assertFalse(r.quarantined)

    def test_novelty_before_external_enforced(self):
        r = run_loop(
            "why freeze",
            **self._base(
                verified_state={},
                inventory={"known": (), "unknown": ("x",)},
                frozen_idea={"frozen_before_external": False},
                external_hits=("study says X",),
            )
        )
        self.assertTrue(r.quarantined)
        self.assertIn("NOVELTY_BEFORE_EXTERNAL", r.violations)
        # quarantined research is presented but never learned
        self.assertEqual(learning_governor(r), "REJECT")

    def test_clean_freeze_allows_research(self):
        r = run_loop(
            "why freeze",
            **self._base(
                verified_state={},
                inventory={"known": (), "unknown": ("x",)},
                frozen_idea={"frozen_before_external": True},
                external_hits=("primary source says Y",),
            )
        )
        self.assertFalse(r.quarantined)
        self.assertEqual(r.external_sources_used, 1)
        self.assertEqual(r.agents_used, 0)

    def test_quality_fields_never_aggregated(self):
        # the report must keep evidence / agents / sources / tokens
        # separate — no single "quality score" field exists
        r = run_loop("q", **self._base())
        for field in ("evidence_ids", "confidence", "agents_used",
                      "external_sources_used"):
            self.assertTrue(hasattr(r, field))
        self.assertFalse(hasattr(r, "quality_score"))

    def test_flow_trace_renders(self):
        from lola_presentation import render_flow
        r = run_loop("what is the decoder buffer size", **self._base())
        out = render_flow(r.trace, task_id="1", external_ai_used=False,
                          evidence_count=len(r.evidence_ids),
                          current_uncertainty="none")
        self.assertIn("TASK #1", out)
        self.assertIn("Intake", out)

    def test_governor_retain_without_verification(self):
        r = run_loop("something complex",
                     **self._base(verified_state={},
                                  inspectable=("a.log",)))
        # inspected but not verified → answer stands, not yet knowledge
        self.assertEqual(learning_governor(r), "RETAIN")

    def test_governor_promote_verified(self):
        from dataclasses import replace
        r = run_loop("what is the decoder buffer size", **self._base())
        r2 = replace(r, transfer_passed=True, regression_passed=True)
        self.assertEqual(learning_governor(r2), "PROMOTE")


if __name__ == "__main__":
    unittest.main()


class FreezeIdeaLoopSeamTests(unittest.TestCase):
    """Integration seam: freeze_idea() output must satisfy the loop's
    novelty-before-external gate. (freeze_idea's purpose is locking the
    idea BEFORE external search; the gate reads that lock.)"""

    def _frozen(self):
        from lola_novelty import build_idea_genome, freeze_idea
        ig = build_idea_genome(
            problem="transfer benchmark fails",
            mechanism="decoder buffer overflow above 4k",
            predictions=("buffer >4k fails",),
            counterpredictions=("small buffer succeeds",),
            falsification_condition="small buffer succeeds",
        )
        return freeze_idea(ig)

    def test_real_frozen_idea_passes_novelty_gate(self):
        from lola_runtime_loop import run_loop
        rep = run_loop(
            "why does the transfer benchmark fail?",
            inventory={"unknown": ("root cause",)},
            frozen_idea=self._frozen(),
            external_hits=("h1",),
        )
        self.assertFalse(rep.quarantined)
        self.assertNotIn("NOVELTY_BEFORE_EXTERNAL", rep.violations)

    def test_unfrozen_idea_still_quarantined(self):
        from lola_runtime_loop import run_loop
        rep = run_loop(
            "why does the transfer benchmark fail?",
            inventory={"unknown": ("root cause",)},
            external_hits=("h1",),  # no frozen idea at all
        )
        self.assertTrue(rep.quarantined)
        self.assertIn("NOVELTY_BEFORE_EXTERNAL", rep.violations)

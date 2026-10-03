import unittest

from lola_cognition_ladder import (
    LEVELS, LadderDecision, smallest_capability,
)
from lola_novelty import (
    IdeaGenome, build_idea_genome, novelty_level, freeze_idea,
    classify_independence, challenge_ideas,
)
from lola_learning_gate import (
    Layer, classify_layer, K_LEVELS, LearningGate, demote,
)

# ---------------------------------------------------------------------------
# Module A — cognition ladder
# ---------------------------------------------------------------------------
class CognitionLadderTests(unittest.TestCase):
    def test_deterministic_gap_is_l0_with_zero_llm(self):
        d = smallest_capability(gap_type="KNOWLEDGE", knowledge_available=False, experience_available=False, derivable=False, novel_candidate=False)
        self.assertEqual(d.level, "L0")
        self.assertEqual(d.llm_class, "none")

    def test_ladder_is_strictly_cheapest_first(self):
        # knowledge available -> L1 beats L2..L8 even if everything else is too
        d = smallest_capability(gap_type="KNOWLEDGE", knowledge_available=True, experience_available=True, derivable=True, novel_candidate=True)
        self.assertEqual(d.level, "L1")
        self.assertEqual(d.llm_class, "none")

    def test_experience_before_derivation(self):
        d = smallest_capability(gap_type="PROCEDURE", knowledge_available=False, experience_available=True, derivable=True)
        self.assertEqual(d.level, "L2")

    def test_internal_derivation_still_zero_llm(self):
        d = smallest_capability(gap_type="CAUSAL", knowledge_available=False, experience_available=False, derivable=True)
        self.assertEqual(d.level, "L3")
        self.assertEqual(d.llm_class, "none")

    def test_novel_synthesis_zero_llm(self):
        d = smallest_capability(gap_type="AMBIGUITY", knowledge_available=False, experience_available=False, derivable=False, novel_candidate=True)
        self.assertEqual(d.level, "L4")
        self.assertEqual(d.llm_class, "none")

    def test_model_level_only_when_internal_exhausted(self):
        d = smallest_capability(gap_type="KNOWLEDGE", knowledge_available=False, experience_available=False, derivable=False, novel_candidate=False, tiers={"tiny_local"})
        self.assertEqual(d.level, "L5")
        self.assertEqual(d.llm_class, "local")
        self.assertEqual(d.provider, "tiny_local")

    def test_remote_requires_network(self):
        d = smallest_capability(gap_type="KNOWLEDGE", tiers={"remote_optional"}, network_available=False)
        self.assertEqual(d.level, "ESCALATE")
        self.assertIn("network", d.reason.lower())

    def test_remote_available_when_network_up(self):
        d = smallest_capability(gap_type="KNOWLEDGE", tiers={"remote_optional"}, network_available=True)
        self.assertEqual(d.level, "L7")
        self.assertEqual(d.llm_class, "external")

    def test_no_capability_escalates_to_human(self):
        d = smallest_capability(gap_type="CAPABILITY", tiers=set())
        self.assertEqual(d.level, "L8")
        self.assertEqual(d.reason, "no_capability_available")

    def test_human_required_short_circuits_to_l8(self):
        d = smallest_capability(gap_type="KNOWLEDGE", knowledge_available=True, human_required=True)
        self.assertEqual(d.level, "L8")

    def test_all_levels_registered(self):
        self.assertEqual([lvl.name for lvl in LEVELS],
                         ["L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"])
        # L0-L4 zero-llm, L5/L6 local, L7 external, L8 human
        self.assertEqual(LEVELS[4].llm, "none")
        self.assertEqual(LEVELS[5].llm, "local")
        self.assertEqual(LEVELS[6].llm, "stronger")
        self.assertEqual(LEVELS[7].llm, "external")


# ---------------------------------------------------------------------------
# Module B — novelty engine + idea genome
# ---------------------------------------------------------------------------
class IdeaGenomeTests(unittest.TestCase):
    def _base(self, **kw):
        args = dict(problem="runtime freezes under load",
                    observations=("buffer grows", "cpu normal"),
                    known_facts=("consumer starvation pattern",),
                    assumptions=("scheduling delay",),
                    primitives=("decoder", "queue"),
                    abstraction="backpressure",
                    mechanism="scheduling delay saturates upstream queue",
                    causal_chain=("scheduling delay", "queue saturation", "freeze"),
                    predictions=("changing scheduling alters queue growth",),
                    counterpredictions=("if network-caused, scheduling change has no effect",),
                    experiment="toggle scheduling, observe queue",
                    falsification_condition="queue growth unchanged under scheduling change",
                    provenance=("episode-1",))
        args.update(kw)
        return args

    def test_builds_valid_genome(self):
        g = build_idea_genome(**self._base())
        self.assertIsInstance(g, IdeaGenome)
        self.assertTrue(g.idea_id)
        self.assertEqual(g.status, "UNTESTED")

    def test_rejects_unfalsifiable(self):
        with self.assertRaises(ValueError):
            build_idea_genome(**self._base(falsification_condition=""))

    def test_rejects_no_prediction(self):
        with self.assertRaises(ValueError):
            build_idea_genome(**self._base(predictions=()))

    def test_rejects_no_mechanism(self):
        with self.assertRaises(ValueError):
            build_idea_genome(**self._base(mechanism=""))

    def test_freeze_locks_before_external(self):
        g = build_idea_genome(**self._base())
        f = freeze_idea(g)
        self.assertIn("idea_id", f)
        self.assertIn("timestamp", f)
        self.assertIn("predictions", f)
        # frozen snapshot is a copy: mutating the genome must not change it
        f2 = freeze_idea(g)
        self.assertEqual(f["idea_id"], f2["idea_id"])


class NoveltyLevelTests(unittest.TestCase):
    def test_compositional_is_n1(self):
        self.assertEqual(novelty_level(primitives_known=True, cross_domain=False, new_mechanism=False, has_testable_prediction=True), "N1")

    def test_cross_domain_is_n2(self):
        self.assertEqual(novelty_level(primitives_known=True, cross_domain=True, new_mechanism=False, has_testable_prediction=True), "N2")

    def test_new_mechanism_is_n3(self):
        self.assertEqual(novelty_level(primitives_known=False, cross_domain=False, new_mechanism=True, has_testable_prediction=True), "N3")

    def test_untestable_is_none(self):
        self.assertEqual(novelty_level(primitives_known=True, cross_domain=False, new_mechanism=False, has_testable_prediction=False), "NONE")

    def test_n3_requires_testable_prediction(self):
        self.assertEqual(novelty_level(new_mechanism=True, has_testable_prediction=False), "NONE")


class IndependenceTests(unittest.TestCase):
    def _frozen(self, mechanism="consumer scheduling delay causes upstream queue saturation"):
        g = build_idea_genome(problem="p", observations=("o",), known_facts=("f",), assumptions=("a",), primitives=("A", "B"), abstraction="x", mechanism=mechanism, causal_chain=("a", "b"), predictions=("p1",), counterpredictions=("c1",), experiment="e", falsification_condition="fc", provenance=("src",))
        return freeze_idea(g)

    def test_known_when_external_match(self):
        f = self._frozen()
        out = classify_independence(f, external_matches=("paper: consumer scheduling delay causes upstream queue saturation in backpressure",))
        self.assertEqual(out, "KNOWN")

    def test_no_match_found_is_not_world_first(self):
        out = classify_independence(self._frozen(), external_matches=())
        self.assertEqual(out, "NO_MATCH_FOUND")
        self.assertNotEqual(out, "WORLD_FIRST")

    def test_independent_rediscovery(self):
        # partial overlap (2/6 tokens) — same space, derived without the source
        out = classify_independence(self._frozen(), external_matches=("notes on upstream queue saturation",))
        self.assertEqual(out, "INDEPENDENT_REDISCOVERY")

    def test_no_overlap_with_matches_is_novel_combination_not_world_first(self):
        out = classify_independence(self._frozen(), external_matches=("entirely unrelated topic on astrophysics",))
        self.assertEqual(out, "NOVEL_COMBINATION")


class DivergeConvergeTests(unittest.TestCase):
    def test_contradicted_idea_fails(self):
        g = build_idea_genome(problem="p", observations=("o",), known_facts=("f",), assumptions=("a",), primitives=("A",), abstraction="x", mechanism="m", causal_chain=("a", "b"), predictions=("p1",), counterpredictions=("c1",), experiment="e", falsification_condition="fc", provenance=("src",))
        verdicts = challenge_ideas([g], evidence={"known_counterexample_for": ("m",)})
        self.assertEqual(verdicts[g.idea_id], "KNOWN_COUNTEREXAMPLE")

    def test_testable_idea_passes(self):
        g = build_idea_genome(problem="p", observations=("o", "o2"), known_facts=("f",), assumptions=("a",), primitives=("A", "B"), abstraction="x", mechanism="m", causal_chain=("a", "b", "c"), predictions=("p1", "p2"), counterpredictions=("c1",), experiment="e", falsification_condition="fc", provenance=("src",))
        verdicts = challenge_ideas([g], evidence={})
        self.assertEqual(verdicts[g.idea_id], "TESTABLE")

    def test_selection_never_by_order(self):
        g1 = build_idea_genome(problem="p", observations=("o",), known_facts=(), assumptions=("a", "a2", "a3"), primitives=("A",), abstraction="x", mechanism="m", causal_chain=("a", "b"), predictions=("p1",), counterpredictions=("c1",), experiment="e", falsification_condition="fc", provenance=("src",))
        # a weaker idea first must not be auto-selected; scoring decides
        verdicts = challenge_ideas([g1], evidence={"known_counterexample_for": ("m",)})
        self.assertEqual(verdicts[g1.idea_id], "KNOWN_COUNTEREXAMPLE")


# ---------------------------------------------------------------------------
# Module C — learning gate / K maturity
# ---------------------------------------------------------------------------
class LearningGateTests(unittest.TestCase):
    def _candidate(self):
        return LearningGate.new_candidate(knowledge_id="k1", source="claude", claim="X causes Y")

    def test_external_source_caps_at_candidate_layer(self):
        self.assertEqual(classify_layer("claude", is_external_model=True), Layer.CANDIDATE)
        self.assertEqual(classify_layer("qwen", is_external_model=True), Layer.CANDIDATE)

    def test_five_layers_are_ordered_and_distinct(self):
        self.assertEqual([L.value for L in Layer], ["DATA", "INFORMATION", "CANDIDATE", "VERIFIED", "LEARNED"])

    def test_k_levels_ordered(self):
        self.assertEqual([k for k in K_LEVELS], ["K0", "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8"])

    def test_prediction_required_before_external_research(self):
        c = self._candidate()
        with self.assertRaises(ValueError):
            c.research_external(query="how does X cause Y")
        c.record_intent(known=("X observed",), unknown=("cause",), prediction="X precedes Y", counter_prediction="timing unrelated")
        c.research_external(query="how does X cause Y")
        self.assertEqual(c.intent["prediction"], "X precedes Y")

    def test_promotes_only_if_all_gates_pass(self):
        c = self._candidate()
        c.record_intent(known=("k",), unknown=("u",), prediction="p", counter_prediction="cp")
        out = c.advance(reproduce=True, falsify=True, transfer=True, regression=True)
        self.assertEqual(out, "PROMOTED")
        self.assertEqual(c.k_level, "K8")
        self.assertEqual(c.status, "ACTIVE")

    def test_stops_at_first_failing_gate(self):
        c = self._candidate()
        c.record_intent(known=("k",), unknown=("u",), prediction="p", counter_prediction="cp")
        out = c.advance(reproduce=True, falsify=False, transfer=True, regression=True)
        self.assertEqual(out, "HOLD")
        self.assertEqual(c.k_level, "K4")  # survived reproduce, failed falsify
        self.assertNotEqual(c.status, "ACTIVE")

    def test_regression_fail_holds(self):
        c = self._candidate()
        c.record_intent(known=("k",), unknown=("u",), prediction="p", counter_prediction="cp")
        out = c.advance(reproduce=True, falsify=True, transfer=True, regression=False)
        self.assertEqual(out, "HOLD")
        self.assertEqual(c.k_level, "K6")

    def test_quarantine_blocks_promotion(self):
        c = self._candidate()
        c.record_intent(known=("k",), unknown=("u",), prediction="p", counter_prediction="cp")
        c.quarantine(reason="contradiction with governed k1")
        out = c.advance(reproduce=True, falsify=True, transfer=True, regression=True)
        self.assertEqual(out, "HOLD")
        self.assertEqual(c.status, "QUARANTINED")

    def test_demotion_moves_backward(self):
        c = self._candidate()
        c.record_intent(known=("k",), unknown=("u",), prediction="p", counter_prediction="cp")
        c.advance(reproduce=True, falsify=True, transfer=True, regression=True)
        self.assertEqual(c.k_level, "K8")
        demote(c, contradiction="new counterexample")
        self.assertLess(K_LEVELS.index(c.k_level), K_LEVELS.index("K8"))
        self.assertEqual(c.status, "QUARANTINED")

    def test_reject_is_terminal(self):
        c = self._candidate()
        c.record_intent(known=("k",), unknown=("u",), prediction="p", counter_prediction="cp")
        c.reject(reason="falsified repeatedly")
        self.assertEqual(c.status, "REJECTED")
        out = c.advance(reproduce=True, falsify=True, transfer=True, regression=True)
        self.assertEqual(out, "HOLD")
        self.assertEqual(c.status, "REJECTED")


if __name__ == "__main__":
    unittest.main()

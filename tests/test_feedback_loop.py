import unittest
from lola_feedback_loop import evaluate_feedback

class FeedbackLoopTests(unittest.TestCase):
    def test_changed_reasoning_requires_metacognitive_recheck(self):
        r=evaluate_feedback(changed_hypotheses=["h1"],unresolved_hypotheses=[],contradictions=0,unknowns=0)
        self.assertEqual(r.status,"RECHECK")
        self.assertEqual(r.recommendation,"REASSESS_REASONING")

    def test_unresolved_output_blocks_consolidation(self):
        r=evaluate_feedback(changed_hypotheses=[],unresolved_hypotheses=["h1"],contradictions=0,unknowns=0)
        self.assertEqual(r.status,"BLOCKED")
        self.assertEqual(r.recommendation,"REDUCE_UNKNOWNS")

    def test_contradiction_has_priority(self):
        r=evaluate_feedback(changed_hypotheses=["h1"],unresolved_hypotheses=[],contradictions=1,unknowns=0)
        self.assertEqual(r.status,"BLOCKED")
        self.assertEqual(r.recommendation,"RESOLVE_CONTRADICTION")

    def test_stable_reasoning_can_continue_to_governance(self):
        r=evaluate_feedback(changed_hypotheses=[],unresolved_hypotheses=[],contradictions=0,unknowns=0)
        self.assertEqual(r.status,"STABLE")
        self.assertFalse(r.execution_authority)

if __name__ == "__main__": unittest.main()

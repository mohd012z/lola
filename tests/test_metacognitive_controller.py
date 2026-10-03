import unittest
from lola_metacognitive_controller import assess_reasoning_state

class MetacognitiveControllerTests(unittest.TestCase):
    def test_low_independence_blocks_confident_action(self):
        r=assess_reasoning_state(evidence_count=4,independent_origins=1,contradictions=0,unknowns=0,failed_replays=0)
        self.assertEqual(r.recommendation,"SEEK_INDEPENDENT_EVIDENCE")
        self.assertFalse(r.action_ready)

    def test_contradiction_requires_resolution(self):
        r=assess_reasoning_state(evidence_count=4,independent_origins=3,contradictions=1,unknowns=0,failed_replays=0)
        self.assertEqual(r.recommendation,"RESOLVE_CONTRADICTION")

    def test_failed_replay_triggers_revision(self):
        r=assess_reasoning_state(evidence_count=4,independent_origins=3,contradictions=0,unknowns=0,failed_replays=1)
        self.assertEqual(r.recommendation,"REVISE_MODEL")

    def test_sufficient_state_is_ready_but_not_authorized(self):
        r=assess_reasoning_state(evidence_count=3,independent_origins=2,contradictions=0,unknowns=0,failed_replays=0)
        self.assertTrue(r.action_ready)
        self.assertFalse(r.execution_authority)

if __name__ == "__main__": unittest.main()

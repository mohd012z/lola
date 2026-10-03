import unittest
from lola_cognitive_cycle import run_cognitive_cycle

class CognitiveCycleTests(unittest.TestCase):
    def test_contradiction_stops_before_consolidation(self):
        r=run_cognitive_cycle(evidence_count=3,independent_origins=2,contradictions=1,unknowns=0,failed_replays=0,recurrence=3,counterexamples=0,transfer_supported=True)
        self.assertEqual(r.metacognitive_recommendation,"RESOLVE_CONTRADICTION")
        self.assertEqual(r.consolidation_status,"BLOCKED")

    def test_failed_replay_forces_revision(self):
        r=run_cognitive_cycle(evidence_count=3,independent_origins=2,contradictions=0,unknowns=0,failed_replays=1,recurrence=3,counterexamples=0,transfer_supported=True)
        self.assertEqual(r.metacognitive_recommendation,"REVISE_MODEL")
        self.assertEqual(r.consolidation_status,"BLOCKED")

    def test_clean_cycle_reaches_candidate_only(self):
        r=run_cognitive_cycle(evidence_count=3,independent_origins=2,contradictions=0,unknowns=0,failed_replays=0,recurrence=3,counterexamples=0,transfer_supported=True)
        self.assertEqual(r.consolidation_status,"CANDIDATE")
        self.assertFalse(r.execution_authority)

if __name__ == "__main__": unittest.main()

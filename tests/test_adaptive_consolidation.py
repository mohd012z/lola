import unittest
from lola_adaptive_consolidation import consolidation_decision

class AdaptiveConsolidationTests(unittest.TestCase):
    def test_unresolved_unknowns_defer_consolidation(self):
        d=consolidation_decision(recurrence=3,independent_origins=3,counterexamples=0,unknowns=1,transfer_supported=True)
        self.assertEqual(d.status,"DEFER")

    def test_counterexample_rejects_candidate(self):
        d=consolidation_decision(recurrence=3,independent_origins=3,counterexamples=1,unknowns=0,transfer_supported=True)
        self.assertEqual(d.status,"REJECT")

    def test_transfer_candidate_requires_transfer_evidence(self):
        d=consolidation_decision(recurrence=3,independent_origins=3,counterexamples=0,unknowns=0,transfer_supported=False,requires_transfer=True)
        self.assertEqual(d.status,"DEFER")

    def test_ready_candidate_is_still_only_candidate(self):
        d=consolidation_decision(recurrence=3,independent_origins=3,counterexamples=0,unknowns=0,transfer_supported=True)
        self.assertEqual(d.status,"CANDIDATE")
        self.assertFalse(d.execution_authority)

if __name__ == "__main__": unittest.main()

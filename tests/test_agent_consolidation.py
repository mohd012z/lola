import unittest
from lola_agent_consolidation import govern_agent_candidate


class AgentConsolidationTests(unittest.TestCase):
    def test_blocks_single_origin(self):
        r=govern_agent_candidate("AR1", ["e1","e2"], ["origin:x"], [], applicability={"domain":"build"})
        self.assertFalse(r.promotable)
        self.assertEqual(r.reason,"insufficient_independence")

    def test_blocks_unresolved_counterexample(self):
        r=govern_agent_candidate("M3", ["e1","e2"], ["o1","o2"], ["bad"], applicability={"domain":"build"})
        self.assertFalse(r.promotable)
        self.assertEqual(r.reason,"counterexamples_unresolved")

    def test_candidate_can_pass_governance_but_has_no_authority(self):
        r=govern_agent_candidate("AR1", ["e1","e2"], ["o1","o2"], [], applicability={"domain":"build"})
        self.assertTrue(r.promotable)
        self.assertFalse(r.execution_authority)


if __name__ == "__main__": unittest.main()

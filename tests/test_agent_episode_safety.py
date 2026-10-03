import unittest
from lola_agent_consolidation import govern_agent_candidate
from lola_experience_compiler import compile_experience

class AgentEpisodeSafetyTests(unittest.TestCase):
    def test_echo_repetition_stays_single_origin_and_not_promotable(self):
        eps=[{"episode_id":"a","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["same"],"echo":True},{"episode_id":"b","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["same"],"echo":True}]
        compiled=compile_experience(eps)
        self.assertEqual(compiled.effective_independent_origins,1)
        r=govern_agent_candidate("M2",["a","b"],compiled.independent_origin_domains,[],applicability={"domain":"x"})
        self.assertFalse(r.promotable)
    def test_recurrence_with_two_origins_and_no_counterexample_is_only_governance_pass(self):
        eps=[{"episode_id":"a","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"]},{"episode_id":"b","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o2"]}]
        compiled=compile_experience(eps)
        r=govern_agent_candidate("AR1",["a","b"],compiled.independent_origin_domains,[],applicability={"domain":"x"})
        self.assertTrue(r.promotable)
        self.assertFalse(r.execution_authority)

if __name__ == "__main__": unittest.main()

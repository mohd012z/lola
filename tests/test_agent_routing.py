import unittest
from lola_agent_routing import CapabilityEvidence, make_routing_candidate, make_antipattern_candidate


class AgentRoutingTests(unittest.TestCase):
    def test_capability_keeps_raw_components(self):
        c=CapabilityEvidence("build","compile",10,8,1,1,0.7,0.9,0.1,2.0,1.0)
        self.assertEqual(c.verified_attempts,8)
        self.assertFalse(hasattr(c,"universal_score"))

    def test_routing_candidate_is_advisory(self):
        r=make_routing_candidate({"domain":"build"},["repo","build","test"],["runtime"],["e1"],["e9"])
        self.assertEqual(r.status,"CANDIDATE")
        self.assertFalse(r.execution_authority)

    def test_antipattern_preserves_recovery_evidence(self):
        a=make_antipattern_candidate("verification", "self-verify", "false confidence", ["f1"], ["r1"])
        self.assertEqual(a.recovery_episode_ids,("r1",))
        self.assertEqual(a.status,"CANDIDATE")


if __name__ == "__main__": unittest.main()

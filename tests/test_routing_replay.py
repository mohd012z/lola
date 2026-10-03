import unittest
from lola_routing_replay import replay_routing_candidate

class RoutingReplayTests(unittest.TestCase):
    def test_counterexample_falsifies_candidate(self):
        r=replay_routing_candidate(["build","test"],[{"sequence":["build","test"],"outcome":"FAILED","independent_origins":["o1"]}])
        self.assertEqual(r.status,"FALSIFIED")
        self.assertEqual(r.failure_count,1)

    def test_successes_do_not_grant_authority(self):
        r=replay_routing_candidate(["build","test"],[{"sequence":["build","test"],"outcome":"VERIFIED","independent_origins":["o1"]},{"sequence":["build","test"],"outcome":"VERIFIED","independent_origins":["o2"]}])
        self.assertEqual(r.status,"SUPPORTED")
        self.assertFalse(r.execution_authority)

    def test_mismatched_sequence_is_not_support(self):
        r=replay_routing_candidate(["build","test"],[{"sequence":["repo","build"],"outcome":"VERIFIED","independent_origins":["o1"]}])
        self.assertEqual(r.support_count,0)

if __name__ == "__main__": unittest.main()

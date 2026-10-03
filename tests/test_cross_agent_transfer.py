import unittest
from lola_cross_agent_transfer import assess_transfer

class CrossAgentTransferTests(unittest.TestCase):
    def test_transfer_requires_distinct_context_and_verified_outcome(self):
        r=assess_transfer([
            {"episode_id":"a","context_fingerprint":"x","agent_id":"A","outcome":"VERIFIED","origin_roots":["o1"]},
            {"episode_id":"b","context_fingerprint":"y","agent_id":"B","outcome":"VERIFIED","origin_roots":["o2"]},
        ])
        self.assertTrue(r.transfer_supported)
        self.assertEqual(r.independent_origin_count,2)

    def test_echoed_origin_does_not_prove_transfer(self):
        r=assess_transfer([
            {"episode_id":"a","context_fingerprint":"x","agent_id":"A","outcome":"VERIFIED","origin_roots":["same"]},
            {"episode_id":"b","context_fingerprint":"y","agent_id":"B","outcome":"VERIFIED","origin_roots":["same"]},
        ])
        self.assertFalse(r.transfer_supported)

    def test_same_context_is_recurrence_not_transfer(self):
        r=assess_transfer([
            {"episode_id":"a","context_fingerprint":"x","agent_id":"A","outcome":"VERIFIED","origin_roots":["o1"]},
            {"episode_id":"b","context_fingerprint":"x","agent_id":"B","outcome":"VERIFIED","origin_roots":["o2"]},
        ])
        self.assertFalse(r.transfer_supported)

if __name__ == "__main__": unittest.main()

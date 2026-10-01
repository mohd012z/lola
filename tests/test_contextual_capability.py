import unittest
from lola_contextual_capability import aggregate_capability

class ContextualCapabilityTests(unittest.TestCase):
    def test_aggregation_keeps_contexts_separate(self):
        rows=aggregate_capability([
            {"agent_id":"A","domain":"build","problem_class":"compile","outcome":"VERIFIED","information_gain":0.8,"cost":2,"latency":1,"duplicate_probe":False},
            {"agent_id":"A","domain":"runtime","problem_class":"crash","outcome":"FAILED","information_gain":0.2,"cost":4,"latency":3,"duplicate_probe":True},
        ])
        self.assertEqual(len(rows),2)
        self.assertNotEqual(rows[0].context_key,rows[1].context_key)

    def test_raw_counts_are_preserved_without_universal_score(self):
        row=aggregate_capability([
            {"agent_id":"A","domain":"build","problem_class":"compile","outcome":"VERIFIED","information_gain":1,"cost":2,"latency":3,"duplicate_probe":False},
            {"agent_id":"A","domain":"build","problem_class":"compile","outcome":"FAILED","information_gain":0,"cost":4,"latency":5,"duplicate_probe":True},
        ])[0]
        self.assertEqual(row.attempts,2)
        self.assertEqual(row.verified_attempts,1)
        self.assertEqual(row.failures,1)
        self.assertFalse(hasattr(row,"universal_score"))

if __name__ == "__main__": unittest.main()

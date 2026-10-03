import unittest
from lola_reasoning_delta import compare_reasoning

class ReasoningDeltaTests(unittest.TestCase):
    def test_changed_conclusion_is_detected(self):
        r=compare_reasoning({"h1":"A","h2":"B"},{"h1":"C","h2":"B"},["h1"])
        self.assertEqual(r.changed_hypothesis_ids,("h1",))
        self.assertEqual(r.unchanged_hypothesis_ids,("h2",))
        self.assertTrue(r.recheck_required)

    def test_same_replayed_conclusion_is_stable(self):
        r=compare_reasoning({"h1":"A"},{"h1":"A"},["h1"])
        self.assertFalse(r.recheck_required)

    def test_missing_replay_output_is_unresolved(self):
        r=compare_reasoning({"h1":"A"},{},["h1"])
        self.assertEqual(r.unresolved_hypothesis_ids,("h1",))
        self.assertTrue(r.recheck_required)

if __name__ == "__main__": unittest.main()

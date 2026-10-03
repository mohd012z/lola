import unittest
from lola_selective_reasoning_replay import plan_selective_replay

class SelectiveReasoningReplayTests(unittest.TestCase):
    def test_changed_knowledge_replays_only_dependent_hypotheses(self):
        deps={"h1":["k1"],"h2":["k2"],"h3":["k1","k3"]}
        r=plan_selective_replay(deps,["k1"])
        self.assertEqual(r.replay_hypothesis_ids,("h1","h3"))
        self.assertEqual(r.untouched_hypothesis_ids,("h2",))

    def test_no_changed_knowledge_means_no_replay(self):
        r=plan_selective_replay({"h1":["k1"]},[])
        self.assertEqual(r.status,"NO_REPLAY")
        self.assertEqual(r.replay_hypothesis_ids,())

    def test_unknown_changed_id_does_not_trigger_unrelated_replay(self):
        r=plan_selective_replay({"h1":["k1"]},["missing"])
        self.assertEqual(r.replay_hypothesis_ids,())

if __name__ == "__main__": unittest.main()

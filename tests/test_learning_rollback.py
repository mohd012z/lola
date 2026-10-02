import unittest
from lola_learning_rollback import rollback_plan

class LearningRollbackTests(unittest.TestCase):
    def test_superseded_candidate_is_quarantined(self):
        r=rollback_plan("cand-v2",["memory:m1","route:r1"],reason="counterexample")
        self.assertEqual(r.status,"QUARANTINE")
        self.assertEqual(r.affected_artifact_ids,("memory:m1","route:r1"))
        self.assertFalse(r.execution_authority)

    def test_empty_impact_is_review_only(self):
        r=rollback_plan("cand-v2",[],reason="replay_failure")
        self.assertEqual(r.status,"REVIEW")

if __name__ == "__main__": unittest.main()

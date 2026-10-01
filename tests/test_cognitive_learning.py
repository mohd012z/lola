import unittest
from lola_cognitive_episode import Episode, PredictionDelta
from lola_cognitive_learning import candidate_from_episode

class ConsolidationTests(unittest.TestCase):
    def episode(self,outcome="VERIFIED",evidence=("e1","e2"),failures=()):
        delta=PredictionDelta("h",{"x":1},{"x":1},True,{})
        return Episode("tr","t",(),(delta,),(),evidence,outcome,failures)
    def test_verified_episode_creates_reversible_candidate(self):
        c=candidate_from_episode(self.episode()); self.assertIsNotNone(c); self.assertTrue(c.reversible); self.assertEqual(c.status,"CANDIDATE")
    def test_partial_failed_and_aborted_do_not_consolidate(self):
        for outcome in ("PARTIAL","FAILED","ABORTED"):
            with self.subTest(outcome=outcome): self.assertIsNone(candidate_from_episode(self.episode(outcome=outcome)))
    def test_missing_evidence_does_not_consolidate(self):
        self.assertIsNone(candidate_from_episode(self.episode(evidence=())))
    def test_verification_failure_does_not_consolidate(self):
        self.assertIsNone(candidate_from_episode(self.episode(failures=("validator_failed",))))

if __name__=="__main__": unittest.main()

import unittest
from lola_revision_engine import revise_candidate

class RevisionEngineTests(unittest.TestCase):
    def test_failed_replay_invalidates_assumption(self):
        r=revise_candidate("AR1",["a1","a2"],["a2"],["e1"],["bad1"])
        self.assertEqual(r.status,"REVISION_REQUIRED")
        self.assertEqual(r.invalidated_assumption_ids,("a2",))
        self.assertIn("bad1",r.preserved_counterexample_ids)

    def test_revision_never_erases_counterexamples(self):
        r=revise_candidate("M2",["a1"],[],["e1"],["bad1","bad2"])
        self.assertEqual(r.preserved_counterexample_ids,("bad1","bad2"))

    def test_clean_candidate_is_unchanged(self):
        r=revise_candidate("M2",["a1"],[],["e1"],[])
        self.assertEqual(r.status,"UNCHANGED")
        self.assertFalse(r.execution_authority)

if __name__ == "__main__": unittest.main()

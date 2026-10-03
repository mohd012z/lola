import unittest
from lola_consolidation_commit_control import prepare_consolidation
from lola_atomic_knowledge_transaction import commit_candidate

class AtomicKnowledgeTransactionTests(unittest.TestCase):
    def _candidate(self, history):
        return prepare_consolidation(history=history,knowledge_id="k1",payload={"rule":"new"},release_status="RELEASE_CANDIDATE",episode_ids=["e1"],evidence_ids=["ev1"],trace_id="t1")

    def test_commit_activates_new_and_supersedes_previous(self):
        history=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"old"}}]
        r=commit_candidate(history,self._candidate(history))
        self.assertEqual(r.status,"COMMITTED")
        states={(x["version"],x["state"]) for x in r.history if x["knowledge_id"]=="k1"}
        self.assertIn((1,"SUPERSEDED"),states)
        self.assertIn((2,"ACTIVE"),states)
        self.assertFalse(r.execution_authority)

    def test_duplicate_or_blocked_candidate_does_not_mutate(self):
        history=[]
        c=prepare_consolidation(history=history,knowledge_id="k1",payload={},release_status="RECHECK",episode_ids=[],evidence_ids=[],trace_id="t1")
        r=commit_candidate(history,c)
        self.assertEqual(r.status,"REJECTED")
        self.assertEqual(r.history,())

    def test_version_conflict_rolls_back(self):
        history=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"old"}}]
        c=self._candidate(history)
        changed=history+[{"knowledge_id":"k1","version":2,"state":"ACTIVE","payload":{"rule":"other"}}]
        r=commit_candidate(changed,c)
        self.assertEqual(r.status,"ROLLED_BACK")
        self.assertEqual(r.history,tuple(changed))

if __name__ == "__main__": unittest.main()

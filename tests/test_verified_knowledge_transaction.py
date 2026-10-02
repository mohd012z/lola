import unittest
from lola_consolidation_commit_control import prepare_consolidation
from lola_verified_knowledge_transaction import execute_verified_transaction

class VerifiedKnowledgeTransactionTests(unittest.TestCase):
    def _candidate(self, history):
        return prepare_consolidation(history=history,knowledge_id="k1",payload={"rule":"new"},release_status="RELEASE_CANDIDATE",episode_ids=["e1"],evidence_ids=["ev1"],trace_id="t1")

    def test_successful_commit_is_postcommit_verified(self):
        before=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"old"}}]
        r=execute_verified_transaction(before,self._candidate(before),transaction_id="tx1")
        self.assertEqual(r.status,"VERIFIED_COMMIT")
        self.assertTrue(r.post_commit_valid)
        self.assertEqual(r.history[-1]["version"],2)
        self.assertFalse(r.execution_authority)

    def test_invalid_candidate_fails_closed_without_mutation(self):
        before=[]
        c=prepare_consolidation(history=before,knowledge_id="k1",payload={},release_status="RECHECK",episode_ids=[],evidence_ids=[],trace_id="t1")
        r=execute_verified_transaction(before,c,transaction_id="tx2")
        self.assertEqual(r.status,"REJECTED")
        self.assertEqual(r.history,())

    def test_forced_postcommit_failure_compensates_and_reverifies_restore(self):
        before=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"old"},"fingerprint":"fp1"}]
        r=execute_verified_transaction(before,self._candidate(before),transaction_id="tx3",expected_fingerprint_override="wrong")
        self.assertEqual(r.status,"RESTORED_VERIFIED")
        self.assertEqual(r.history,tuple(before))
        self.assertTrue(r.recovery_record["compensated"])
        self.assertTrue(r.restore_valid)

if __name__ == "__main__": unittest.main()

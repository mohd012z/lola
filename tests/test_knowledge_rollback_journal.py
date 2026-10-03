import unittest
from lola_knowledge_rollback_journal import create_rollback_journal, compensate_failed_commit

class KnowledgeRollbackJournalTests(unittest.TestCase):
    def test_journal_captures_verified_precommit_state(self):
        before=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","fingerprint":"fp1"}]
        j=create_rollback_journal(before,"k1",expected_version=2,transaction_id="tx1")
        self.assertEqual(j.status,"READY")
        self.assertEqual(j.previous_active_version,1)
        self.assertEqual(j.transaction_id,"tx1")
        self.assertFalse(j.execution_authority)

    def test_failed_postcommit_restores_original_history(self):
        before=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","fingerprint":"fp1"}]
        journal=create_rollback_journal(before,"k1",2,"tx1")
        broken=[{"knowledge_id":"k1","version":1,"state":"SUPERSEDED","fingerprint":"fp1"},{"knowledge_id":"k1","version":2,"state":"ACTIVE","fingerprint":"wrong"}]
        r=compensate_failed_commit(broken,journal,post_commit_valid=False)
        self.assertEqual(r.status,"RESTORED")
        self.assertEqual(r.history,tuple(before))
        self.assertTrue(r.recovery_record["compensated"])

    def test_valid_postcommit_does_not_rollback(self):
        before=[{"knowledge_id":"k1","version":1,"state":"ACTIVE"}]
        journal=create_rollback_journal(before,"k1",2,"tx1")
        after=[{"knowledge_id":"k1","version":1,"state":"SUPERSEDED"},{"knowledge_id":"k1","version":2,"state":"ACTIVE"}]
        r=compensate_failed_commit(after,journal,post_commit_valid=True)
        self.assertEqual(r.status,"NO_ROLLBACK")
        self.assertEqual(r.history,tuple(after))

if __name__ == "__main__": unittest.main()

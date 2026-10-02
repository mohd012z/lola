import unittest
from lola_post_commit_verifier import verify_committed_knowledge

class PostCommitVerifierTests(unittest.TestCase):
    def test_valid_version_chain_verifies(self):
        h=[{"knowledge_id":"k1","version":1,"state":"SUPERSEDED"},{"knowledge_id":"k1","version":2,"state":"ACTIVE","supersedes_version":1,"fingerprint":"fp2"}]
        r=verify_committed_knowledge(h,"k1",2,"fp2")
        self.assertEqual(r.status,"VERIFIED")
        self.assertTrue(r.valid)

    def test_two_active_versions_fail(self):
        h=[{"knowledge_id":"k1","version":1,"state":"ACTIVE"},{"knowledge_id":"k1","version":2,"state":"ACTIVE","supersedes_version":1,"fingerprint":"fp2"}]
        r=verify_committed_knowledge(h,"k1",2,"fp2")
        self.assertEqual(r.status,"INVARIANT_FAILURE")
        self.assertFalse(r.valid)

    def test_readback_fingerprint_mismatch_fails(self):
        h=[{"knowledge_id":"k1","version":2,"state":"ACTIVE","fingerprint":"wrong"}]
        r=verify_committed_knowledge(h,"k1",2,"expected_fingerprint="fp2")
        self.assertEqual(r.status,"READBACK_MISMATCH")

if __name__ == "__main__": unittest.main()

import unittest
from lola_consolidation_commit_control import prepare_consolidation

class ConsolidationCommitControlTests(unittest.TestCase):
    def test_release_candidate_creates_next_version_candidate(self):
        history=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"old"}}]
        r=prepare_consolidation(history=history,knowledge_id="k1",payload={"rule":"new"},release_status="RELEASE_CANDIDATE",episode_ids=["e2","e1"],evidence_ids=["ev1"],trace_id="t1")
        self.assertEqual(r.status,"CANDIDATE")
        self.assertEqual(r.version,2)
        self.assertEqual(r.supersedes_version,1)
        self.assertEqual(r.episode_ids,("e1","e2"))
        self.assertFalse(r.execution_authority)

    def test_non_release_state_cannot_consolidate(self):
        r=prepare_consolidation(history=[],knowledge_id="k1",payload={"x":1},release_status="RECHECK",episode_ids=[],evidence_ids=[],trace_id="t1")
        self.assertEqual(r.status,"BLOCKED")

    def test_duplicate_payload_and_provenance_is_suppressed(self):
        history=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"same"},"episode_ids":["e1"],"evidence_ids":["ev1"],"trace_id":"t1"}]
        r=prepare_consolidation(history=history,knowledge_id="k1",payload={"rule":"same"},release_status="RELEASE_CANDIDATE",episode_ids=["e1"],evidence_ids=["ev1"],trace_id="t1")
        self.assertEqual(r.status,"DUPLICATE")
        self.assertIsNone(r.version)

if __name__ == "__main__": unittest.main()

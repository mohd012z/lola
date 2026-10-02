import unittest
from lola_memory_retrieval import retrieve_knowledge

class MemoryRetrievalTests(unittest.TestCase):
    def test_returns_latest_active_version_only(self):
        records=[
            {"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"old"}},
            {"knowledge_id":"k1","version":2,"state":"ACTIVE","supersedes_version":1,"payload":{"rule":"new"}},
        ]
        out=retrieve_knowledge(records,"k1")
        self.assertEqual(out.version,2)
        self.assertEqual(out.payload["rule"],"new")

    def test_quarantined_latest_version_blocks_fallback_to_stale(self):
        records=[
            {"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"old"}},
            {"knowledge_id":"k1","version":2,"state":"QUARANTINED","supersedes_version":1,"payload":{"rule":"bad"}},
        ]
        out=retrieve_knowledge(records,"k1")
        self.assertEqual(out.status,"BLOCKED")
        self.assertIsNone(out.payload)

    def test_unknown_knowledge_is_miss(self):
        out=retrieve_knowledge([],"missing")
        self.assertEqual(out.status,"MISS")

if __name__ == "__main__": unittest.main()

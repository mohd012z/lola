import unittest
from lola_agent_memory_refresh import refresh_agent_memory

class AgentMemoryRefreshTests(unittest.TestCase):
    def test_stale_reference_forces_refresh(self):
        records=[
            {"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"old"}},
            {"knowledge_id":"k1","version":2,"state":"ACTIVE","supersedes_version":1,"payload":{"rule":"new"}},
        ]
        r=refresh_agent_memory(records,{"k1":1})
        self.assertEqual(r.status,"REFRESH_REQUIRED")
        self.assertEqual(r.refreshes,(('k1',1,2),))
        self.assertFalse(r.execution_authority)

    def test_quarantined_latest_blocks_refresh(self):
        records=[
            {"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"old"}},
            {"knowledge_id":"k1","version":2,"state":"QUARANTINED","supersedes_version":1,"payload":{"rule":"bad"}},
        ]
        r=refresh_agent_memory(records,{"k1":1})
        self.assertEqual(r.status,"BLOCKED")
        self.assertEqual(r.blocked_ids,("k1",))

    def test_current_snapshot_needs_no_refresh(self):
        records=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":{"rule":"ok"}}]
        self.assertEqual(refresh_agent_memory(records,{"k1":1}).status,"CURRENT")

if __name__ == "__main__": unittest.main()

import unittest
from lola_stale_memory_detector import detect_stale_memory

class StaleMemoryDetectorTests(unittest.TestCase):
    def test_superseded_reference_is_stale(self):
        records=[{"knowledge_id":"k1","version":1,"state":"ACTIVE"},{"knowledge_id":"k1","version":2,"state":"ACTIVE","supersedes_version":1}]
        r=detect_stale_memory(records,"k1",1)
        self.assertTrue(r.stale)
        self.assertEqual(r.reason,"SUPERSEDED")

    def test_quarantined_latest_is_blocked(self):
        records=[{"knowledge_id":"k1","version":1,"state":"QUARANTINED"}]
        r=detect_stale_memory(records,"k1",1)
        self.assertTrue(r.stale)
        self.assertEqual(r.reason,"QUARANTINED")

    def test_current_active_is_not_stale(self):
        records=[{"knowledge_id":"k1","version":1,"state":"ACTIVE"}]
        self.assertFalse(detect_stale_memory(records,"k1",1).stale)

if __name__ == "__main__": unittest.main()

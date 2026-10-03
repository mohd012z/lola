import unittest
from lola_knowledge_lifecycle import KnowledgeVersion, KnowledgeLifecycle

class KnowledgeLifecycleTests(unittest.TestCase):
    def test_superseded_version_becomes_stale(self):
        k=KnowledgeLifecycle([KnowledgeVersion("k1",1,"ACTIVE"),KnowledgeVersion("k1",2,"ACTIVE",supersedes_version=1)])
        self.assertEqual(k.status("k1",1),"SUPERSEDED")
        self.assertEqual(k.status("k1",2),"ACTIVE")

    def test_quarantined_latest_version_is_not_usable(self):
        k=KnowledgeLifecycle([KnowledgeVersion("k1",1,"QUARANTINED")])
        self.assertFalse(k.usable("k1",1))

    def test_version_gap_rejected(self):
        with self.assertRaises(ValueError):
            KnowledgeLifecycle([KnowledgeVersion("k1",1,"ACTIVE"),KnowledgeVersion("k1",3,"ACTIVE",supersedes_version=1)])

if __name__ == "__main__": unittest.main()

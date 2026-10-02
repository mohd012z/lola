import unittest
from lola_cognitive_fabric import KIPEnvelope
from lola_cognitive_evidence import corroborate

def obs(source, value, event_id, evidence_id):
    return KIPEnvelope(id=event_id,kind="observation",topic="x",source=source,payload={"value":value},evidence_id=evidence_id)

class EvidenceTests(unittest.TestCase):
    def test_independent_sources_promote_e2(self):
        r=corroborate("claim",[obs("a",1,"1","e1"),obs("b",1,"2","e2")])
        self.assertTrue(r.independently_corroborated); self.assertEqual(r.evidence_grade,"E2_CORROBORATED")
    def test_same_source_does_not_promote(self):
        r=corroborate("claim",[obs("a",1,"1","e1"),obs("a",1,"2","e2")])
        self.assertFalse(r.independently_corroborated)
    def test_duplicate_event_does_not_promote(self):
        r=corroborate("claim",[obs("a",1,"1","e1"),obs("b",1,"1","e2")])
        self.assertFalse(r.independently_corroborated)
    def test_conflict_reported(self):
        r=corroborate("claim",[obs("a",1,"1","e1"),obs("b",2,"2","e2")])
        self.assertTrue(r.conflicts); self.assertFalse(r.independently_corroborated)

if __name__ == "__main__": unittest.main()

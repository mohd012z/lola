import unittest
from lola_cognitive_sources import EvidenceGrade, InternalSourceAdapter, SourceRecord

class CognitiveSourceTests(unittest.TestCase):
    def test_normalizes_provenance_and_grade(self):
        env = InternalSourceAdapter().normalize(SourceRecord("build-1","build","result","build.status",{"value":"PASS"},EvidenceGrade.E0_DIRECT,.99,"ev-1"), task_id="t1", trace_id="tr1")
        self.assertEqual(env.evidence_grade, "E0_DIRECT")
        self.assertEqual(env.provenance["source_type"], "build")
        self.assertEqual(env.evidence_id, "ev-1")
    def test_rejects_missing_provenance(self):
        with self.assertRaises(ValueError): SourceRecord("","build","result","x",{})

if __name__ == "__main__": unittest.main()

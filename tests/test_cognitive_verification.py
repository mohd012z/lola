import tempfile, unittest
from lola_cognitive_fabric import CognitiveFabric, KIPEnvelope
from lola_cognitive_evidence import CorroborationResult

class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.NamedTemporaryFile(delete=False); self.tmp.close(); self.f=CognitiveFabric(self.tmp.name)
    def test_supported_is_not_verified(self):
        self.f.propose_hypothesis("t","h","build passes",predicts={"build.status":"PASS"})
        self.f.ingest(KIPEnvelope(kind="observation",topic="build.status",source="a",task_id="t",payload={"entity":"build","property":"status","value":"PASS"},direct=True,reliability=.9,evidence_grade="E0_DIRECT",evidence_id="e1",provenance={"source_type":"build"}))
        r=self.f.evaluate_hypothesis("t","h"); self.assertEqual(r["status"],"SUPPORTED"); self.assertNotIn("h",self.f.state("t").verified_claims)
    def test_explicit_verification(self):
        self.f.propose_hypothesis("t","h","build passes",predicts={"build.status":"PASS"})
        for src,eid in (("a","e1"),("b","e2")):
            self.f.ingest(KIPEnvelope(kind="observation",topic="build.status",source=src,task_id="t",payload={"entity":"build","property":"status","value":"PASS"},direct=True,reliability=.9,evidence_grade="E0_DIRECT",evidence_id=eid,provenance={"source_type":"build"}))
        self.f.evaluate_hypothesis("t","h")
        c=CorroborationResult("build.status",("e1","e2"),("a","b"),"E2_CORROBORATED",())
        r=self.f.verify_hypothesis("t","h",corroboration=c,validators={"reproduce":True}); self.assertTrue(r["verified"]); self.assertIn("h",self.f.state("t").verified_claims)
    def test_validator_blocks_with_valid_observation_context(self):
        self.f.propose_hypothesis("t","h","x",predicts={"x.y":1})
        self.f.ingest(KIPEnvelope(kind="observation",topic="x.y",source="a",task_id="t",payload={"entity":"x","property":"y","value":1},direct=True,reliability=.9,evidence_grade="E0_DIRECT",evidence_id="e1",provenance={"source_type":"test"}))
        self.f.evaluate_hypothesis("t","h")
        c=CorroborationResult("x.y",("e1","e2"),("a","b"),"E2_CORROBORATED",())
        self.assertEqual(self.f.verify_hypothesis("t","h",corroboration=c,validators={"reproduce":False})["reason"],"validator_failed")

if __name__=="__main__":unittest.main()

import tempfile
import unittest

from lola_cognitive_fabric import CognitiveFabric, KIPEnvelope, Kind, PathClass
from lola_cognitive_evidence import CorroborationResult


class CognitiveFabricTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.fabric = CognitiveFabric(self.tmp.name)

    def test_hybrid_route_is_cognitive_and_durable(self):
        event = KIPEnvelope(kind=Kind.EVIDENCE.value, topic="evidence.test", source="tester", task_id="t1", payload={"value": 1}, durable=True)
        paths = self.fabric.router.classify(event)
        self.assertIn(PathClass.COGNITIVE, paths)
        self.assertIn(PathClass.DURABLE, paths)

    def test_duplicate_is_idempotent(self):
        event = KIPEnvelope(id="fixed", kind="observation", topic="runtime.x", source="a", task_id="t1", payload={})
        self.assertTrue(self.fabric.ingest(event)["accepted"])
        self.assertFalse(self.fabric.ingest(event)["accepted"])

    def test_trace_context_is_propagated_to_durable_event(self):
        event = KIPEnvelope(kind="evidence", topic="evidence.x", source="a", task_id="t1", trace_id="tr1", payload={}, durable=True)
        self.fabric.ingest(event)
        replay = self.fabric.events.replay("t1")
        self.assertEqual(replay[0]["trace_id"], "tr1")

    def test_capability_registry_prefers_reliable_source(self):
        self.fabric.registry.register("weak", ["build.status"], reliability=.4)
        self.fabric.registry.register("strong", ["build.status"], reliability=.9)
        self.assertEqual(self.fabric.registry.select("build.status")[0].source_id, "strong")

    def test_contradiction_trips_epistemic_fuse(self):
        for value in ("PASS", "FAIL"):
            self.fabric.ingest(KIPEnvelope(kind="observation", topic="runtime.build", source="a", task_id="t1", payload={"entity":"build","property":"status","value":value}, direct=True, reliability=.9))
        self.assertTrue(self.fabric.meta.metrics(self.fabric.state("t1"))["epistemic_fuse"])

    def test_rank_unknowns_prefers_high_information_low_cost_probe(self):
        self.fabric.registry.register("build", ["build.status"], reliability=.95)
        self.fabric.registry.register("runtime", ["runtime.state"], reliability=.6)
        state = self.fabric.state("t1")
        state.unknowns.update({"build.status", "runtime.state"})
        ranked = self.fabric.rank_unknowns("t1", costs={"build.status":.1, "runtime.state":.8})
        self.assertEqual(ranked[0]["unknown"], "build.status")

    def test_causal_delta_finds_first_divergence(self):
        state = self.fabric.state("t1")
        state.world.update({"a":1,"b":3})
        result = self.fabric.causal_delta("t1", [("a",1),("b",2)])
        self.assertEqual(result["key"], "b")

    def test_hypothesis_requires_explicit_verification(self):
        self.fabric.propose_hypothesis("t1", "h1", "build passes", predicts={"build.status":"PASS"})
        observations=[]
        for source,eid in (("build","e1"),("runtime","e2")):
            event=KIPEnvelope(kind="observation",topic="build.status",source=source,task_id="t1",payload={"entity":"build","property":"status","value":"PASS"},direct=True,reliability=.95,evidence_grade="E0_DIRECT",evidence_id=eid,provenance={"source_type":source})
            self.fabric.ingest(event); observations.append(event)
        result=self.fabric.evaluate_hypothesis("t1","h1")
        self.assertEqual(result["status"],"SUPPORTED")
        self.assertNotIn("h1",self.fabric.snapshot("t1")["verified_claims"])
        corroboration=CorroborationResult("build.status",("e1","e2"),("build","runtime"),"E2_CORROBORATED",())
        verified=self.fabric.verify_hypothesis("t1","h1",corroboration=corroboration,validators={"reproduce":True})
        self.assertTrue(verified["verified"])
        self.assertIn("h1",self.fabric.snapshot("t1")["verified_claims"])


if __name__ == "__main__":
    unittest.main()

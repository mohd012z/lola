from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lola_cognitive_fabric import CognitiveFabric, KIPEnvelope, PathClass


class CognitiveFabricTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name) / "events.jsonl"
        self.fabric = CognitiveFabric(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def event(self, **overrides):
        data = dict(
            kind="observation",
            topic="runtime.state",
            source="runtime-probe",
            task_id="t1",
            payload={"entity": "dashboard", "property": "present", "value": True},
            reliability=0.95,
            direct=True,
            durable=True,
        )
        data.update(overrides)
        return KIPEnvelope(**data)

    def test_hybrid_route_is_cognitive_and_durable(self):
        result = self.fabric.ingest(self.event())
        self.assertTrue(result["accepted"])
        self.assertIn(PathClass.COGNITIVE.value, result["paths"])
        self.assertIn(PathClass.DURABLE.value, result["paths"])
        self.assertEqual(True, self.fabric.snapshot("t1")["world"]["dashboard.present"])

    def test_duplicate_is_idempotent(self):
        event = self.event(id="same-event")
        self.assertTrue(self.fabric.ingest(event)["accepted"])
        self.assertFalse(self.fabric.ingest(event)["accepted"])
        self.assertEqual(1, len(self.fabric.events.replay("t1")))

    def test_contradiction_trips_epistemic_fuse(self):
        self.fabric.ingest(self.event(id="a"))
        second = self.event(
            id="b",
            source="artifact-inspector",
            payload={"entity": "dashboard", "property": "present", "value": False},
        )
        result = self.fabric.ingest(second)
        self.assertTrue(result["meta"]["epistemic_fuse"])
        self.assertEqual("CROSSCHECK", result["next"])

    def test_causal_delta_finds_first_divergence(self):
        self.fabric.ingest(self.event(
            id="source",
            topic="evidence.source",
            payload={"entity": "pipeline", "property": "source", "value": True},
        ))
        self.fabric.ingest(self.event(
            id="artifact",
            topic="evidence.artifact",
            payload={"entity": "pipeline", "property": "artifact", "value": False},
        ))
        delta = self.fabric.causal_delta("t1", [
            ("pipeline.source", True),
            ("pipeline.artifact", True),
            ("pipeline.runtime", True),
        ])
        self.assertEqual(1, delta["index"])
        self.assertEqual("pipeline.artifact", delta["key"])

    def test_capability_registry_prefers_reliable_source(self):
        self.fabric.registry.register("a", ["runtime.logs"], reliability=0.6)
        self.fabric.registry.register("b", ["runtime.logs"], reliability=0.95)
        self.assertEqual("b", self.fabric.registry.select("runtime.logs")[0].source_id)


if __name__ == "__main__":
    unittest.main()

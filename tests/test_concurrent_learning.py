import threading
import unittest

from lola_concurrent_learning import (
    ConcurrentLearningBus,
    LearningCandidate,
    LearningState,
    SourceKind,
    drain_to_gate,
    run_concurrent_learning_smoke,
)
from lola_learning_gate import Layer


class ConcurrentLearningBusTests(unittest.TestCase):
    def test_exact_duplicate_is_accepted_once(self):
        bus = ConcurrentLearningBus()
        candidate = LearningCandidate(
            source_kind=SourceKind.RUNTIME,
            source_id="run-1",
            proposition="startup reached ready state",
            state=LearningState.OBSERVED,
        )
        self.assertTrue(bus.publish(candidate))
        self.assertFalse(bus.publish(candidate))
        self.assertEqual(1, len(bus))

    def test_context_changes_candidate_identity(self):
        bus = ConcurrentLearningBus()
        a = LearningCandidate(SourceKind.CODE, "repo", "API works", {"android": "15"})
        b = LearningCandidate(SourceKind.CODE, "repo", "API works", {"android": "17"})
        self.assertEqual(2, bus.publish_many((a, b)))

    def test_parallel_publish_is_deduplicated(self):
        bus = ConcurrentLearningBus()
        candidate = LearningCandidate(SourceKind.TEST, "suite", "case passed", state=LearningState.OBSERVED)
        threads = [threading.Thread(target=bus.publish, args=(candidate,)) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, len(bus))

    def test_drain_is_bounded_and_ordered(self):
        bus = ConcurrentLearningBus()
        candidates = [LearningCandidate(SourceKind.USER, str(i), f"fact-{i}") for i in range(3)]
        bus.publish_many(candidates)
        self.assertEqual(tuple(candidates[:2]), bus.drain(2))
        self.assertEqual((candidates[2],), bus.snapshot())

    def test_negative_limit_rejected(self):
        with self.assertRaises(ValueError):
            ConcurrentLearningBus().drain(-1)


class GateBridgeTests(unittest.TestCase):
    def test_bridge_never_promotes(self):
        bus = ConcurrentLearningBus()
        c = LearningCandidate(SourceKind.TEST, "suite", "case passed",
                              state=LearningState.OBSERVED)
        bus.publish(c)
        pairs = drain_to_gate(bus)
        self.assertEqual(len(pairs), 1)
        _, g = pairs[0]
        self.assertEqual(g.status, "CANDIDATE")
        self.assertIn(g.k_level, ("K0", "K1", "K2"))

    def test_model_sourced_capped_at_candidate_layer(self):
        bus = ConcurrentLearningBus()
        c = LearningCandidate(SourceKind.MODEL, "qwen", "it should be faster",
                              state=LearningState.IMAGINED)
        bus.publish(c)
        _, g = drain_to_gate(bus)[0]
        self.assertEqual(g.layer, Layer.CANDIDATE)  # external-model rule

    def test_runtime_sourced_is_information(self):
        bus = ConcurrentLearningBus()
        c = LearningCandidate(SourceKind.RUNTIME, "run-1", "reached ready",
                              state=LearningState.OBSERVED)
        bus.publish(c)
        _, g = drain_to_gate(bus)[0]
        self.assertEqual(g.layer, Layer.INFORMATION)

    def test_deterministic_gate_identity_across_reingest(self):
        c = LearningCandidate(SourceKind.NOVEL, "nc-1", "predictive paging")
        b1 = ConcurrentLearningBus(); b1.publish(c)
        id1 = drain_to_gate(b1)[0][1].knowledge_id
        b2 = ConcurrentLearningBus(); b2.publish(c)
        id2 = drain_to_gate(b2)[0][1].knowledge_id
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("LC-"))

    def test_single_writer_convergence(self):
        bus = ConcurrentLearningBus()
        for i in range(3):
            bus.publish(LearningCandidate(SourceKind.USER, str(i), f"fact-{i}"))
        self.assertEqual(len(drain_to_gate(bus, limit=2)), 2)
        self.assertEqual(len(drain_to_gate(bus)), 1)
        self.assertEqual(drain_to_gate(bus), tuple())


class SmokeTests(unittest.TestCase):
    def test_smoke_passes(self):
        r = run_concurrent_learning_smoke()
        self.assertTrue(r["passed"], r["failed"])
        self.assertGreaterEqual(r["total"], 10)


if __name__ == "__main__":
    unittest.main()

import threading
import unittest

from lola_concurrent_learning import (
    ConcurrentLearningBus,
    LearningCandidate,
    LearningState,
    SourceKind,
)


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


if __name__ == "__main__":
    unittest.main()

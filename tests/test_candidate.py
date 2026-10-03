"""Tests for the NovelCandidate v1 layer (lola_candidate).

Deterministic, zero-model: immutable candidate records, structural
fingerprints (wording-invariant identity), the candidate state machine
(VERIFIED is unreachable without an observed episode), deterministic
operators, lineage, and the episode-aware duplicate gate — the thread's
two-run acceptance test (RUN #1 fails and records; RUN #2 suppresses the
failed structure and admits a different one).
"""
import tempfile
import unittest
from dataclasses import FrozenInstanceError

from lola_candidate import (
    Episode,
    NovelCandidate,
    CandidateStore,
    STATE_CRITICIZED,
    STATE_FALSIFIED,
    STATE_IMAGINED,
    STATE_TESTED,
    STATE_VERIFIED,
    apply_operator,
    diverge,
    gate,
    record_outcome,
    run_candidate_smoke,
    structural_fingerprint,
)


def make_seed():
    return NovelCandidate(
        title="Prefetch documentation before the engine requests it",
        mechanism="Predict next retrieval and warm the doc cache early",
        resource="documentation",
        operation="preload",
        trigger="before request",
        target="latency",
        problem_id="P-1",
        goal="reduce retrieval latency",
        assumptions=("retrieval is predictable",),
        predictions=("retrieval latency decreases",),
    )


class FingerprintTests(unittest.TestCase):
    def test_stable_across_wording(self):
        a = make_seed()
        b = NovelCandidate(
            title="Warm the documentation cache ahead of demand",
            mechanism="Completely different prose about the same structure",
            resource="documentation",
            operation="preload",
            trigger="before request",
            target="latency",
        )
        self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertTrue(a.fingerprint.startswith("FP-"))

    def test_differs_for_different_structure(self):
        a = make_seed()
        b = NovelCandidate(
            title="Lazy-load the model",
            mechanism="Load GGUF only on demand",
            resource="model",
            operation="lazy",
            trigger="on-demand",
        )
        self.assertNotEqual(a.fingerprint, b.fingerprint)

    def test_deterministic(self):
        a = structural_fingerprint(resource="documentation", operation="preload",
                                   trigger="before request", target="latency")
        b = structural_fingerprint(resource="documentation", operation="preload",
                                   trigger="before request", target="latency")
        self.assertEqual(a, b)


class CandidateRecordTests(unittest.TestCase):
    def test_requires_title_and_mechanism(self):
        with self.assertRaises(ValueError):
            NovelCandidate(title="", mechanism="x")
        with self.assertRaises(ValueError):
            NovelCandidate(title="t", mechanism="")

    def test_immutable(self):
        c = make_seed()
        with self.assertRaises(FrozenInstanceError):
            c.title = "hacked"  # type: ignore[reportAttributeAccessIssue]  # intentional: must raise

    def test_id_deterministic_and_stable(self):
        a = make_seed()
        b = make_seed()
        self.assertEqual(a.candidate_id, b.candidate_id)
        self.assertTrue(a.candidate_id.startswith("NC-"))

    def test_state_machine_blocks_direct_verify(self):
        with self.assertRaises(ValueError):
            make_seed().transition(STATE_VERIFIED)

    def test_state_machine_evidenced_path(self):
        c = make_seed()
        self.assertEqual(c.state, STATE_IMAGINED)
        c2 = c.transition(STATE_CRITICIZED).transition(STATE_TESTED).transition(STATE_VERIFIED)
        self.assertEqual(c2.state, STATE_VERIFIED)
        # terminal states admit no moves
        with self.assertRaises(ValueError):
            c2.transition(STATE_FALSIFIED)


class OperatorTests(unittest.TestCase):
    def test_operator_returns_new_child_with_lineage(self):
        seed = make_seed()
        child = apply_operator(seed, "LAZY")
        self.assertNotEqual(child.candidate_id, seed.candidate_id)
        self.assertEqual(child.parent_ids, (seed.candidate_id,))
        self.assertIn("LAZY", child.transformations)
        self.assertEqual(child.state, STATE_IMAGINED)
        # structural change -> different fingerprint
        self.assertNotEqual(child.fingerprint, seed.fingerprint)

    def test_unknown_operator_rejected(self):
        with self.assertRaises(ValueError):
            apply_operator(make_seed(), "MAKE_IT_SO")

    def test_diverge_dedupes_structurally(self):
        kids = diverge(make_seed())
        fps = [k.fingerprint for k in kids]
        self.assertEqual(len(fps), len(set(fps)))
        self.assertGreaterEqual(len(kids), 5)
        # deterministic: same input, same population
        self.assertEqual([k.candidate_id for k in kids],
                         [k2.candidate_id for k2 in diverge(make_seed())])


class GateTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = CandidateStore(self._td.name + "/cand.db")

    def tearDown(self):
        self.store.close()
        self._td.cleanup()

    def test_empty_store_admits(self):
        g = gate(make_seed(), self.store)
        self.assertEqual(g["verdict"], "NOVEL")

    def test_stored_candidate_is_duplicate(self):
        seed = make_seed()
        self.store.add_candidate(seed)
        g = gate(seed, self.store)
        self.assertEqual(g["verdict"], "DUPLICATE")
        self.assertIn(seed.candidate_id, g["existing"])

    def test_known_failure_suppressed_via_episode(self):
        seed = make_seed()
        store2 = CandidateStore(self._td.name + "/c2.db")
        try:
            ep, state = record_outcome(store2, seed, "FAIL",
                                       predicted={"latency_ms": 95},
                                       observed={"latency_ms": 180})
            self.assertEqual(state, STATE_FALSIFIED)
            # same structure, never stored as a candidate
            retry = NovelCandidate(
                title="Retry: preload docs before request",
                mechanism="Warm the predicted documentation cache",
                resource="documentation",
                operation="preload",
                trigger="before request",
                target="latency",
            )
            g = gate(retry, store2)
            self.assertEqual(g["verdict"], "KNOWN_FAILURE")
            self.assertIn(ep.episode_id, g["episodes"])
        finally:
            store2.close()

    def test_two_run_acceptance(self):
        """The thread's literal milestone: RUN #1 fails and records; RUN #2
        retrieves that episode and suppresses the duplicate, admitting a
        different candidate."""
        seed = make_seed()
        self.store.add_candidate(seed)
        ep, _ = record_outcome(self.store, seed, "FAIL",
                               predicted={"x": 1}, observed={"x": 2})
        self.assertTrue(ep.episode_id.startswith("EP-"))
        # run 2: the failed structure comes back in new wording
        retry = NovelCandidate(
            title="Again: preload docs before request",
            mechanism="New words, same structure",
            resource="documentation",
            operation="preload",
            trigger="before request",
            target="latency",
        )
        self.assertEqual(gate(retry, self.store)["verdict"], "DUPLICATE")
        # and a genuinely different structure is admitted
        different = NovelCandidate(
            title="Lazy-load the model",
            mechanism="Load GGUF only on demand",
            resource="model",
            operation="lazy",
            trigger="on-demand",
        )
        self.assertEqual(gate(different, self.store)["verdict"], "NOVEL")

    def test_pass_episode_verifies_via_observation_only(self):
        c = NovelCandidate(title="Lazy-load the model", mechanism="Load GGUF on demand",
                           resource="model", operation="lazy", trigger="on-demand")
        self.store.add_candidate(c)
        _, state = record_outcome(self.store, c, "PASS",
                                  predicted={"ram_mb": 700}, observed={"ram_mb": 610},
                                  delta={"ram_mb": -90})
        self.assertEqual(state, STATE_VERIFIED)
        self.assertEqual(self.store.get_state(c.candidate_id), STATE_VERIFIED)

    def test_inconclusive_stays_tested(self):
        c = NovelCandidate(title="Compress context", mechanism="Quantize the working set",
                           resource="context", operation="compress")
        self.store.add_candidate(c)
        _, state = record_outcome(self.store, c, "INCONCLUSIVE",
                                  predicted={"a": 1}, observed={"a": 1})
        self.assertEqual(state, STATE_TESTED)
        self.assertEqual(self.store.get_state(c.candidate_id), STATE_TESTED)


class EpisodeTests(unittest.TestCase):
    def test_unknown_outcome_rejected(self):
        with self.assertRaises(ValueError):
            Episode(candidate_id="NC-X", fingerprint="FP-Y", outcome="MAYBE")

    def test_ids_deterministic(self):
        a = Episode(candidate_id="NC-A", fingerprint="FP-A", outcome="FAIL")
        b = Episode(candidate_id="NC-A", fingerprint="FP-A", outcome="FAIL")
        self.assertEqual(a.episode_id, b.episode_id)
        self.assertTrue(a.episode_id.startswith("EP-"))

    def test_state_move_mapping(self):
        self.assertEqual(
            Episode(candidate_id="c", fingerprint="f", outcome="FALSIFIED").candidate_state_move,
            STATE_FALSIFIED)
        self.assertEqual(
            Episode(candidate_id="c", fingerprint="f", outcome="PARTIAL_SUCCESS").candidate_state_move,
            STATE_TESTED)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = CandidateStore(self._td.name + "/s.db")

    def tearDown(self):
        self.store.close()
        self._td.cleanup()

    def test_add_candidate_idempotent(self):
        c = make_seed()
        self.assertTrue(self.store.add_candidate(c))
        self.assertFalse(self.store.add_candidate(c))

    def test_lineage(self):
        c = make_seed()
        self.store.add_candidate(c)
        child = apply_operator(c, "CACHE")
        self.store.link(c.candidate_id, child.candidate_id, "evolved_into")
        self.assertIn(child.candidate_id, self.store.lineage(c.candidate_id, "evolved_into"))
        with self.assertRaises(ValueError):
            self.store.link("a", "b", "made_up_relation")

    def test_rebuildable_cache(self):
        self.store.close()
        import os
        os.remove(self._td.name + "/s.db")
        store2 = CandidateStore(self._td.name + "/s.db")
        try:
            row = store2.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='candidates'"
            ).fetchone()
            self.assertIsNotNone(row)
        finally:
            store2.close()


class SmokeTests(unittest.TestCase):
    def test_smoke_passes(self):
        r = run_candidate_smoke()
        self.assertTrue(r["passed"], r["failed"])
        self.assertGreaterEqual(r["total"], 16)


if __name__ == "__main__":
    unittest.main()

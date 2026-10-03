"""Tests for the LOLA Knowledge Store (LKS) v1.

Covers: form-invariant semantic dedup, repetition-as-counter, Law 1 at the
storage boundary (only E3-E6 may verify/falsify), ConflictSet (contradictions
never averaged away), graph edges stored once, export policy gate, container
round-trip (magic/version/CRC), corruption detection, version gating,
BASE + DELTA + compact equivalence, varint/zigzag sanity.
"""
import json
import unittest

from lola_lks import (
    MAGIC,
    NOT_VERIFIED,
    STALE,
    TRUSTED,
    UNBOUND,
    AtomState,
    ConflictSet,
    E2_REFERENCE,
    E3_DETERMINISTIC,
    E4_TEST,
    E5_RUNTIME,
    E6_REPEATED,
    E0_UNSUPPORTED,
    E1_INDIRECT,
    EvidenceRef,
    ExportPolicy,
    KnowledgeAtom,
    LKSFile,
    LKSStore,
    Transport,
    _decode_container,
    inputs_match,
    run_lks_smoke,
    varint_decode,
    varint_encode,
    zigzag_decode,
    zigzag_encode,
)


def _atom(aid, subject, relation, obj, context="", **kw):
    return KnowledgeAtom(atom_id=aid, subject=subject, relation=relation,
                         object=obj, context=context, **kw)


class DedupTests(unittest.TestCase):
    def test_form_invariant_merge(self):
        s = LKSStore()
        a = s.add_atom(_atom("A1", "MQL5_Compiler", "rejects_pattern",
                             "Legacy_Objects_Total_Call", context="Build XYZ"))
        b = s.add_atom(_atom("A2", "MQL5 Compiler", "rejects pattern",
                             "Legacy Objects Total Call", context="build xyz"))
        self.assertEqual(a, b)
        self.assertEqual(len(s._atoms), 1)

    def test_repetition_is_counter_not_copies(self):
        s = LKSStore()
        s.add_atom(_atom("A1", "x", "y", "z"))
        s.add_atom(_atom("A2", "X", "Y", "Z"))
        s.add_atom(_atom("A3", " x ", "y", " z "))
        self.assertEqual(len(s._atoms), 1)
        self.assertEqual(s.get("A1").occurrences, 3)

    def test_distinct_context_is_distinct_atom(self):
        s = LKSStore()
        s.add_atom(_atom("A1", "x", "y", "z", context="env A"))
        s.add_atom(_atom("A2", "x", "y", "z", context="env B"))
        self.assertEqual(len(s._atoms), 2)

    def test_duplicate_evidence_not_stacked(self):
        s = LKSStore()
        ev = EvidenceRef("EV1", "ab" * 32, E2_REFERENCE)
        s.add_atom(_atom("A1", "x", "y", "z", evidence=(ev,)))
        s.add_atom(_atom("A2", "x", "y", "z", evidence=(ev,)))
        self.assertEqual(len(s.get("A1").evidence), 1)


class Law1Tests(unittest.TestCase):
    def setUp(self):
        self.s = LKSStore()
        self.aid = self.s.add_atom(_atom("A1", "x", "y", "z"))

    def test_model_statement_cannot_verify(self):
        for cls in (E0_UNSUPPORTED, E1_INDIRECT, E2_REFERENCE):
            with self.assertRaises(PermissionError):
                self.s.record_verification(self.aid,
                                           EvidenceRef("EV", "cd" * 32, cls))

    def test_deterministic_can_verify(self):
        self.s.record_verification(
            self.aid, EvidenceRef("EV", "cd" * 32, E3_DETERMINISTIC))
        self.assertEqual(self.s.get(self.aid).state, AtomState.VERIFIED.value)

    def test_test_runtime_repeated_can_verify(self):
        for cls in (E4_TEST, E5_RUNTIME, E6_REPEATED):
            s = LKSStore()
            aid = s.add_atom(_atom("B1", "p", "q", "r"))
            s.record_verification(aid, EvidenceRef("EV", "ef" * 32, cls))
            self.assertEqual(s.get(aid).state, AtomState.VERIFIED.value)

    def test_only_e3_e6_can_falsify(self):
        with self.assertRaises(PermissionError):
            self.s.record_falsification(self.aid,
                                        EvidenceRef("EV", "11" * 32, E2_REFERENCE))
        self.s.record_falsification(self.aid,
                                    EvidenceRef("EV", "11" * 32, E3_DETERMINISTIC))
        self.assertEqual(self.s.get(self.aid).state, AtomState.FALSIFIED.value)

    def test_verified_state_not_constructible_directly(self):
        # A caller CAN construct an atom claiming VERIFIED (dataclass freedom),
        # but the store's ONLY state-changing path is record_verification —
        # ingestion of a VERIFIED-claim atom keeps the claim (provenance of the
        # claim is its problem), and re-verification still requires E3-E6.
        s = LKSStore()
        a = _atom("A9", "x", "y", "z", state=AtomState.VERIFIED.value)
        s.add_atom(a)
        with self.assertRaises(PermissionError):
            s.record_verification("A9", EvidenceRef("EV", "22" * 32, E1_INDIRECT))


class ConflictTests(unittest.TestCase):
    def test_conflict_requires_two_claims(self):
        with self.assertRaises(ValueError):
            ConflictSet("p", (("only", "EV1"),))

    def test_conflict_unresolved_and_stable(self):
        s = LKSStore()
        s.add_conflict(ConflictSet("X works", (("yes", "E1"), ("no", "E2"))))
        s.add_conflict(ConflictSet("X works", (("yes", "E3"), ("no", "E4"))))
        self.assertEqual(len(s.conflicts()), 1)
        self.assertEqual(s.conflicts()[0].status, "UNRESOLVED")

    def test_bad_status_rejected(self):
        with self.assertRaises(ValueError):
            ConflictSet("p", (("a", "E1"), ("b", "E2")), status="MAYBE")


class GraphTests(unittest.TestCase):
    def test_edge_stored_once(self):
        s = LKSStore()
        a = s.add_atom(_atom("A1", "x", "y", "z"))
        b = s.add_atom(_atom("B1", "p", "q", "r"))
        s.add_edge(a, "uses", b)
        s.add_edge(a, "uses", b)
        self.assertEqual(len(s._graph), 1)

    def test_edge_requires_known_atoms(self):
        s = LKSStore()
        a = s.add_atom(_atom("A1", "x", "y", "z"))
        with self.assertRaises(KeyError):
            s.add_edge(a, "uses", "GHOST")


class ExportPolicyTests(unittest.TestCase):
    def test_local_only_never_cloud(self):
        s = LKSStore()
        aid = s.add_atom(_atom("L1", "x", "y", "z",
                               export_policy=ExportPolicy.LOCAL_ONLY.value))
        self.assertTrue(all(a.atom_id != aid for a in s.exportable(Transport.CLOUD)))
        self.assertTrue(all(a.atom_id != aid for a in s.exportable(Transport.EXPORT)))
        self.assertTrue(any(a.atom_id == aid for a in s.exportable(Transport.LOCAL)))

    def test_model_local_stays_local_model(self):
        s = LKSStore()
        aid = s.add_atom(_atom("M1", "x", "y", "z",
                               export_policy=ExportPolicy.MODEL_LOCAL.value))
        self.assertTrue(any(a.atom_id == aid for a in s.exportable(Transport.LOCAL_MODEL)))
        self.assertTrue(all(a.atom_id != aid for a in s.exportable(Transport.CLOUD)))

    def test_shareable_everywhere(self):
        s = LKSStore()
        aid = s.add_atom(_atom("S1", "x", "y", "z",
                               export_policy=ExportPolicy.SHAREABLE.value))
        for t in Transport:
            self.assertTrue(any(a.atom_id == aid for a in s.exportable(t)))


class ContainerTests(unittest.TestCase):
    def _store(self):
        s = LKSStore()
        a = s.add_atom(_atom("A1", "MQL5", "rejects", "LegacyCall",
                             context="build",
                             evidence=(EvidenceRef("EV1", "aa" * 32, E3_DETERMINISTIC),)))
        s.record_verification(a, EvidenceRef("EV2", "bb" * 32, E4_TEST))
        b = s.add_atom(_atom("B1", "PositionAPI", "defined_in", "MQL5"))
        s.add_edge(a, "uses", b)
        s.add_conflict(ConflictSet("MQL5 version", (("1", "EV3"), ("2", "EV4"))))
        return s

    def test_roundtrip(self):
        s = self._store()
        s2 = _decode_container(s.to_base_bytes())
        self.assertEqual(set(s2._atoms), set(s._atoms))
        self.assertEqual(s2.get("A1").state, AtomState.VERIFIED.value)
        self.assertEqual(len(s2._graph), 1)
        self.assertEqual(len(s2.conflicts()), 1)
        self.assertEqual(len(s2.get("A1").evidence), 2)

    def test_magic(self):
        self.assertEqual(self._store().to_base_bytes()[:6], MAGIC)

    def test_bad_magic_rejected(self):
        blob = self._store().to_base_bytes()
        with self.assertRaises(ValueError):
            _decode_container(b"XXXXXX" + blob[6:])

    def test_version_gate(self):
        blob = self._store().to_base_bytes()
        with self.assertRaises(ValueError):
            _decode_container(blob[:6] + bytes([9, 0]) + blob[8:])

    def test_corruption_detected(self):
        blob = bytearray(self._store().to_base_bytes())
        blob[len(blob) // 2] ^= 0xFF
        with self.assertRaises(ValueError):
            _decode_container(bytes(blob))

    def test_truncated_rejected(self):
        blob = self._store().to_base_bytes()
        with self.assertRaises(ValueError):
            _decode_container(blob[:len(blob) - 5])

    def test_deterministic_bytes(self):
        s = self._store()
        self.assertEqual(s.to_base_bytes(), s.to_base_bytes())


class DeltaTests(unittest.TestCase):
    def test_base_plus_delta_snapshot(self):
        s = LKSStore()
        s.add_atom(_atom("A1", "x", "y", "z"))
        f = LKSFile.new()
        f.base = s.to_base_bytes()
        f.append_delta([{"op": "add_atom",
                         "atom": json.dumps({"atom_id": "D1", "subject": "Kotlin",
                                             "relation": "compiles_with",
                                             "object": "Gradle", "context": "ci"})}])
        snap = f.snapshot()
        self.assertIn("D1", snap._atoms)
        self.assertIn("A1", snap._atoms)

    def test_compact_equivalence(self):
        s = LKSStore()
        a = s.add_atom(_atom("A1", "x", "y", "z"))
        s.record_verification(a, EvidenceRef("EV", "cc" * 32, E3_DETERMINISTIC))
        f = LKSFile.new()
        f.base = s.to_base_bytes()
        f.append_delta([{"op": "add_atom",
                         "atom": json.dumps({"atom_id": "D1", "subject": "p",
                                             "relation": "q", "object": "r"})}])
        before = {k: (v.state, v.occurrences) for k, v in f.snapshot()._atoms.items()}
        c = f.compact()
        self.assertEqual(c.deltas, [])
        after = {k: (v.state, v.occurrences) for k, v in c.snapshot()._atoms.items()}
        self.assertEqual(before, after)

    def test_delta_rejects_unknown_op(self):
        f = LKSFile.new()
        with self.assertRaises(ValueError):
            f.append_delta([{"op": "rm_rf", "x": "1"}])

    def test_delta_corruption_detected(self):
        f = LKSFile.new()
        f.append_delta([{"op": "add_atom",
                         "atom": json.dumps({"atom_id": "D1", "subject": "a",
                                             "relation": "b", "object": "c"})}])
        bad = bytearray(f.deltas[0])
        bad[-1] ^= 0xFF
        f.deltas[0] = bytes(bad)
        with self.assertRaises(ValueError):
            f.snapshot()


class FreshnessTests(unittest.TestCase):
    """Thread weakness #11: a cached PASS is not evidence for a new
    candidate. Only reuse verified knowledge when its relevant inputs
    match — otherwise STALE, never silently green."""

    def _verified(self, inputs=None):
        s = LKSStore()
        aid = s.add_atom(_atom("A1", "Build", "passes_with", "dep-v1",
                               context="ci"))
        s.record_verification(aid, EvidenceRef("EV", "aa" * 32, E4_TEST,
                                               inputs=inputs or ()))
        return s, aid

    def test_trusted_when_inputs_match(self):
        s, aid = self._verified((("source_hash", "aa" * 32),
                                 ("test_hash", "bb" * 32)))
        self.assertEqual(s.freshness(aid, {"source_hash": "aa" * 32,
                                           "test_hash": "bb" * 32}), TRUSTED)

    def test_stale_when_source_changes(self):
        s, aid = self._verified((("source_hash", "aa" * 32),
                                 ("test_hash", "bb" * 32)))
        self.assertEqual(s.freshness(aid, {"source_hash": "cc" * 32,
                                           "test_hash": "bb" * 32}), STALE)

    def test_stale_when_test_changes(self):
        s, aid = self._verified((("source_hash", "aa" * 32),
                                 ("test_hash", "bb" * 32)))
        self.assertEqual(s.freshness(aid, {"source_hash": "aa" * 32,
                                           "test_hash": "dd" * 32}), STALE)

    def test_stale_when_binding_input_absent(self):
        s, aid = self._verified((("source_hash", "aa" * 32),))
        self.assertEqual(s.freshness(aid, {"unrelated": "ee" * 32}), STALE)

    def test_extra_current_inputs_do_not_invalidate(self):
        s, aid = self._verified((("source_hash", "aa" * 32),))
        self.assertEqual(s.freshness(aid, {"source_hash": "aa" * 32,
                                           "env_hash": "ff" * 32}), TRUSTED)

    def test_unbound_legacy_verified_reported_not_trusted(self):
        s, aid = self._verified(())
        self.assertEqual(s.freshness(aid, {}), UNBOUND)
        self.assertNotEqual(s.freshness(aid, {}), TRUSTED)

    def test_not_verified_state(self):
        s = LKSStore()
        aid = s.add_atom(_atom("A1", "x", "y", "z"))
        self.assertEqual(s.freshness(aid, {}), NOT_VERIFIED)

    def test_falsified_is_not_verified(self):
        s, aid = self._verified((("source_hash", "aa" * 32),))
        s.record_falsification(aid, EvidenceRef("EV2", "bb" * 32, E3_DETERMINISTIC))
        self.assertEqual(s.freshness(aid, {}), NOT_VERIFIED)

    def test_e2_evidence_cannot_be_a_verifying_ref(self):
        # Law 1 symmetry: E0-E2 can never verify, so they can never be the
        # freshness basis either.
        s, aid = self._verified((("source_hash", "aa" * 32),))
        with self.assertRaises(PermissionError):
            s.record_verification(aid, EvidenceRef("EV3", "cc" * 32, E2_REFERENCE,
                                                   inputs=(("source_hash", "cc" * 32),)))
        self.assertEqual(s.freshness(aid, {"source_hash": "aa" * 32}), TRUSTED)

    def test_bindings_survive_container_roundtrip(self):
        s, aid = self._verified((("source_hash", "aa" * 32),
                                 ("test_hash", "bb" * 32)))
        s2 = _decode_container(s.to_base_bytes())
        self.assertEqual(s2.freshness(aid, {"source_hash": "aa" * 32,
                                            "test_hash": "bb" * 32}), TRUSTED)
        self.assertEqual(s2.freshness(aid, {"source_hash": "99" * 32,
                                            "test_hash": "bb" * 32}), STALE)

    def test_bindings_survive_delta_compact(self):
        s, aid = self._verified((("source_hash", "aa" * 32),))
        f = LKSFile.new()
        f.base = s.to_base_bytes()
        c = f.compact()
        s2 = c.snapshot()
        self.assertEqual(s2.freshness(aid, {"source_hash": "aa" * 32}), TRUSTED)

    def test_invalid_binding_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceRef("EV", "aa" * 32, E3_DETERMINISTIC, inputs=(("name", ""),))
        with self.assertRaises(ValueError):
            EvidenceRef("EV", "aa" * 32, E3_DETERMINISTIC, inputs=(("", "hh" * 32),))

    def test_inputs_match_helper(self):
        ref = EvidenceRef("EV", "aa" * 32, E3_DETERMINISTIC,
                          inputs=(("a", "1"), ("b", "2")))
        self.assertTrue(inputs_match(ref, {"a": "1", "b": "2", "c": "3"}))
        self.assertFalse(inputs_match(ref, {"a": "1", "b": "X"}))
        self.assertFalse(inputs_match(ref, {"a": "1"}))


class CodecTests(unittest.TestCase):
    def test_varint(self):
        for v in (0, 1, 127, 128, 300, 16384, 100000, 2**31):
            d, pos = varint_decode(varint_encode(v), 0)
            self.assertEqual(d, v)
            self.assertEqual(pos, len(varint_encode(v)))

    def test_varint_small(self):
        self.assertEqual(len(varint_encode(1)), 1)
        self.assertEqual(len(varint_encode(120)), 1)
        self.assertLessEqual(len(varint_encode(1000)), 2)
        self.assertLessEqual(len(varint_encode(100000)), 3)

    def test_zigzag(self):
        for v in (0, 1, -1, 100, -100, 100000, -100000):
            self.assertEqual(zigzag_decode(zigzag_encode(v)), v)

    def test_varint_rejects_negative(self):
        with self.assertRaises(ValueError):
            varint_encode(-1)


class SmokeTests(unittest.TestCase):
    def test_smoke_all_pass(self):
        r = run_lks_smoke()
        self.assertTrue(r["passed"], r["failed"])
        self.assertGreaterEqual(r["total"], 15)


if __name__ == "__main__":
    unittest.main()

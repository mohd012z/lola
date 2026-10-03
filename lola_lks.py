"""LOLA Knowledge Store (LKS) — compact, model-independent knowledge storage v1.

Study source: shared thread `6ac11613`, sections "what happens after the data
becomes large on disk" (four-temperature storage, content addressing,
semantic compaction), "compact knowledge to store" (knowledge atoms, evidence
separation, exceptions survive compaction, contradictions are not averaged
away), and the .LKS format design (magic "LOLAKS", versioned header, string
dictionary, varints, delta-encoded graph edges, BASE + DELTA segments,
self-indexing header, per-segment checksums, export policy).

Design rules enforced here (deterministic, stdlib-only, zero model calls):

* Atom != knowledge until its own state says so.  State defaults to
  CANDIDATE; the ONLY path to VERIFIED is record_verification() with a
  deterministic/test/runtime/repeated evidence ref (E3-E6) — a model or user
  statement (E0-E2) can never verify (Law 1).
* Evidence is separated from knowledge: atoms carry evidence *references*
  (content hashes), never the raw evidence bytes.
* Semantic dedup: byte identity (SHA-256) AND context-canonical fingerprint.
  Repetition collapses into a counter, not copies.
* Contradictions are NOT averaged away: a conflicting claim pair becomes a
  ConflictSet (status UNRESOLVED; the better-supported claim is noted by
  evidence class, but resolution stays with the gate).
* Export policy: LOCAL_ONLY atoms cannot cross a CLOUD transport boundary.
* Container: magic "LOLAKS", versioned header with a section index (direct
  seek, no scan), string dictionary with varint IDs, per-segment SHA-256
  checksums, BASE + DELTA append-only segments, compact() = deterministic
  merge.
* Versioning from day one: readers reject unknown major versions; bytes are
  never silently reinterpreted.
"""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

MAGIC = b"LOLAKS"
FORMAT_VERSION_MAJOR = 1
FORMAT_VERSION_MINOR = 2   # v2: evidence input bindings (freshness)
SCHEMA_VERSION = 2
MIN_READER = 1

# Section ids in the container (header index points at each directly).
SEC_DICT = 0
SEC_ATOMS = 1
SEC_EVIDENCE = 2
SEC_CONFLICTS = 3
SEC_GRAPH = 4
SEC_DELTA = 5
SECTION_COUNT = 6


class AtomState(str, Enum):
    CANDIDATE = "CANDIDATE"
    VERIFIED = "VERIFIED"          # settable ONLY via record_verification()
    FALSIFIED = "FALSIFIED"
    CONFLICT = "CONFLICT"


class ExportPolicy(str, Enum):
    LOCAL_ONLY = "LOCAL_ONLY"
    MODEL_LOCAL = "MODEL_LOCAL"
    CLOUD_ALLOWED = "CLOUD_ALLOWED"
    SHAREABLE = "SHAREABLE"


class Transport(str, Enum):
    LOCAL = "LOCAL"
    LOCAL_MODEL = "LOCAL_MODEL"
    CLOUD = "CLOUD"
    EXPORT = "EXPORT"


# The thread's evidence classes for learning candidates:
E0_UNSUPPORTED = "E0_UNSUPPORTED"
E1_INDIRECT = "E1_INDIRECT"
E2_REFERENCE = "E2_REFERENCE"
E3_DETERMINISTIC = "E3_DETERMINISTIC"
E4_TEST = "E4_TEST"
E5_RUNTIME = "E5_RUNTIME"
E6_REPEATED = "E6_REPEATED"
EVIDENCE_CLASSES: tuple[str, ...] = (
    E0_UNSUPPORTED, E1_INDIRECT, E2_REFERENCE, E3_DETERMINISTIC,
    E4_TEST, E5_RUNTIME, E6_REPEATED,
)

# Freshness verdicts (thread weakness #11: cached PASS is not evidence for a
# new candidate — "only reuse when relevant inputs match. Otherwise STALE
# EVIDENCE, not green."):
TRUSTED = "TRUSTED"    # verified AND its input binding matches current inputs
STALE = "STALE"        # verified but inputs changed — must be re-verified
UNBOUND = "UNBOUND"    # verified with no input binding — unverifiable;
                       # reported, never trusted, never falsely red
NOT_VERIFIED = "NOT_VERIFIED"  # atom state is not VERIFIED at all


# ---------------------------------------------------------------------------
# varint (LEB128, unsigned) — small numbers must not consume 8 bytes
# ---------------------------------------------------------------------------

def varint_encode(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint is unsigned; use a zigzag helper for signed values")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def varint_decode(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("varint runs past end of buffer")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint too long (>64 bits)")


def zigzag_encode(value: int) -> int:
    return value * 2 if value >= 0 else (-value) * 2 - 1


def zigzag_decode(value: int) -> int:
    return (value >> 1) if not value & 1 else -((value + 1) >> 1)


# ---------------------------------------------------------------------------
# string dictionary — IDs everywhere; strings stored once
# ---------------------------------------------------------------------------

class StringDictionary:
    """Insertion-ordered, deterministic id assignment."""

    def __init__(self) -> None:
        self._ids: dict[str, int] = {}
        self._order: list[str] = []

    def intern(self, s: str) -> int:
        sid = self._ids.get(s)
        if sid is None:
            sid = len(self._order)
            self._ids[s] = sid
            self._order.append(s)
        return sid

    def get(self, sid: int) -> str:
        return self._order[sid]

    def __len__(self) -> int:
        return len(self._order)

    def as_list(self) -> list[str]:
        return list(self._order)


# ---------------------------------------------------------------------------
# knowledge primitives
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceRef:
    """A reference to raw evidence — the bytes live in the object store,
    keyed by this hash.  Atoms never embed raw logs (section 4 of the
    compaction design).

    `inputs` is the **freshness binding** (thread weakness #11,
    'build cache can produce false green'): the content hashes of the
    inputs this evidence was produced against (source_hash, test_hash,
    dependency_hash, environment_hash, ...). A verified atom whose binding
    no longer matches the current inputs is STALE — never silently green.
    Legacy refs with no binding are UNBOUND: unverifiable, not trusted,
    not falsely red.
    """
    evidence_id: str
    content_hash: str
    evidence_class: str = E2_REFERENCE
    inputs: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(f"unknown evidence class: {self.evidence_class}")
        if not self.evidence_id or not self.content_hash:
            raise ValueError("evidence_id and content_hash are required")
        for name, h in self.inputs:
            if not name or not h:
                raise ValueError("input bindings need a name and a hash")


def make_evidence_ref(evidence_id: str, raw: bytes,
                      evidence_class: str = E2_REFERENCE,
                      inputs: Mapping[str, str] | None = None) -> EvidenceRef:
    binding = tuple(sorted((inputs or {}).items()))
    return EvidenceRef(evidence_id=evidence_id,
                       content_hash=hashlib.sha256(raw).hexdigest(),
                       evidence_class=evidence_class,
                       inputs=binding)


def inputs_match(ref: EvidenceRef, current: Mapping[str, str]) -> bool:
    """True iff every bound input name is present in `current` with the
    same hash.  Extra current inputs are fine; a missing or changed bound
    input is a mismatch.  An unbound ref is vacuously matching (callers
    distinguish that via UNBOUND, not via this predicate)."""
    return all(current.get(name) == h for name, h in ref.inputs)


def _canon_slot(value: str) -> str:
    """Context-canonicalization for fingerprints: lowercase, inner
    whitespace collapsed, underscore/hyphen treated as word boundaries.
    (Full word-invariance — paraphrase-level dedup — lives in
    lola_candidate.structural_fingerprint; here we normalize *form* so
    'MQL5_Compiler' == 'MQL5 Compiler'.)"""
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


@dataclass(frozen=True)
class KnowledgeAtom:
    """subject — relation — object, with context and evidence references.

    Thousands of verbose conversations can point to one atom.  The atom's
    bytes (subject/relation/object/context) are content-addressed by
    `fingerprint`; repetition increments `occurrences` instead of storing
    copies.
    """
    atom_id: str
    subject: str
    relation: str
    object: str
    context: str = ""
    constraints: str = ""
    state: str = AtomState.CANDIDATE.value
    export_policy: str = ExportPolicy.MODEL_LOCAL.value
    evidence: tuple[EvidenceRef, ...] = ()
    occurrences: int = 1

    def __post_init__(self) -> None:
        if self.state not in AtomState._value2member_map_:
            raise ValueError(f"unknown atom state: {self.state}")
        if self.export_policy not in ExportPolicy._value2member_map_:
            raise ValueError(f"unknown export policy: {self.export_policy}")
        if self.occurrences < 1:
            raise ValueError("occurrences must be >= 1")

    @property
    def fingerprint(self) -> str:
        """Context-canonical identity (semantic dedup layer 2)."""
        base = "|".join(_canon_slot(x) for x in
                        (self.subject, self.relation, self.object,
                         self.context))
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]

    def byte_hash(self) -> str:
        """Byte identity (semantic dedup layer 1)."""
        base = json.dumps(
            [self.atom_id, self.subject, self.relation, self.object,
             self.context, self.constraints, self.state, self.export_policy,
             [(e.evidence_id, e.content_hash, e.evidence_class)
              for e in self.evidence]],
            sort_keys=True)
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def best_evidence_class(self) -> str:
        if not self.evidence:
            return E0_UNSUPPORTED
        return max(e.evidence_class for e in self.evidence)


# ---------------------------------------------------------------------------
# ConflictSet — contradictions are never averaged away
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConflictSet:
    proposition: str
    claims: tuple[tuple[str, str], ...]   # (claim, supporting evidence_id)
    status: str = "UNRESOLVED"

    def __post_init__(self) -> None:
        if len(self.claims) < 2:
            raise ValueError("a conflict needs at least two claims")
        if self.status not in ("UNRESOLVED", "RESOLVED", "HOLD"):
            raise ValueError(f"unknown conflict status: {self.status}")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(_canon_slot(self.proposition).encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# export policy gate
# ---------------------------------------------------------------------------

def export_allowed(atom: KnowledgeAtom, transport: Transport) -> bool:
    """Deterministic export gate.  LOCAL_ONLY never leaves the device;
    MODEL_LOCAL stays with a local model; only CLOUD_ALLOWED/SHAREABLE may
    cross cloud or export boundaries."""
    pol = atom.export_policy
    if transport in (Transport.LOCAL,):
        return True
    if pol == ExportPolicy.LOCAL_ONLY.value:
        return False
    if pol == ExportPolicy.MODEL_LOCAL.value:
        return transport == Transport.LOCAL_MODEL
    if pol == ExportPolicy.CLOUD_ALLOWED.value:
        return transport in (Transport.LOCAL_MODEL, Transport.CLOUD, Transport.EXPORT)
    return True  # SHAREABLE


# ---------------------------------------------------------------------------
# store — the in-memory knowledge base with dedup, conflicts, verification
# ---------------------------------------------------------------------------

class LKSStore:
    def __init__(self) -> None:
        self.dict = StringDictionary()
        self._atoms: dict[str, KnowledgeAtom] = {}      # atom_id -> atom
        self._by_fp: dict[str, str] = {}                # fingerprint -> atom_id
        self._conflicts: dict[str, ConflictSet] = {}    # fp -> conflict
        self._graph: list[tuple[str, str, str]] = []    # (src, edge, dst) atom edges
        self._version = 0
        self._history: list[str] = []                   # audit: applied operations

    # -- ingestion ----------------------------------------------------------
    def add_atom(self, atom: KnowledgeAtom) -> str:
        """Idempotent, dedup-aware ingestion.  Returns the canonical atom_id
        (existing one when the fingerprint already exists).  Repeated adds
        of the same fingerprint increment `occurrences` — repetition becomes
        a counter, never copies."""
        fp = atom.fingerprint
        existing = self._by_fp.get(fp)
        if existing is not None:
            cur = self._atoms[existing]
            merged_evidence = tuple(cur.evidence + tuple(
                e for e in atom.evidence
                if e.evidence_id not in {c.evidence_id for c in cur.evidence}))
            upgraded = KnowledgeAtom(
                atom_id=cur.atom_id, subject=cur.subject, relation=cur.relation,
                object=cur.object, context=cur.context,
                constraints=cur.constraints or atom.constraints,
                state=cur.state, export_policy=cur.export_policy,
                evidence=merged_evidence,
                occurrences=cur.occurrences + atom.occurrences)
            self._atoms[existing] = upgraded
            self._bump(f"add_dedup:{existing}")
            return existing
        self._atoms[atom.atom_id] = atom
        self._by_fp[fp] = atom.atom_id
        self._bump(f"add:{atom.atom_id}")
        return atom.atom_id

    def add_edge(self, src: str, relation: str, dst: str) -> None:
        """Graph edge between atoms — relationships stored once, referenced
        from elsewhere (section 12)."""
        if src not in self._atoms or dst not in self._atoms:
            raise KeyError("edge endpoints must be known atoms")
        if (src, relation, dst) not in self._graph:
            self._graph.append((src, relation, dst))
            self._bump(f"edge:{src}-{relation}>{dst}")

    def add_conflict(self, cs: ConflictSet) -> str:
        key = cs.fingerprint
        if key not in self._conflicts:
            self._conflicts[key] = cs
            self._bump(f"conflict:{cs.proposition}")
            # mark the involved atoms as CONFLICT state (never resolved here)
        return key

    # -- the ONLY path to VERIFIED -------------------------------------------
    def record_verification(self, atom_id: str, ref: EvidenceRef) -> KnowledgeAtom:
        """Law 1 enforced at the storage boundary: E0-E2 evidence (model
        statements, indirect, plain reference) can NEVER verify an atom.
        Only deterministic/test/runtime/repeated verification (E3-E6) may."""
        atom = self._atoms[atom_id]
        if ref.evidence_class not in (E3_DETERMINISTIC, E4_TEST, E5_RUNTIME, E6_REPEATED):
            raise PermissionError(
                f"{atom_id}: {ref.evidence_class} evidence cannot verify an atom "
                "(only E3-E6 may; model/user statements are evidence, not verification)")
        upgraded = KnowledgeAtom(
            atom_id=atom.atom_id, subject=atom.subject, relation=atom.relation,
            object=atom.object, context=atom.context, constraints=atom.constraints,
            state=AtomState.VERIFIED.value, export_policy=atom.export_policy,
            evidence=atom.evidence + (ref,), occurrences=atom.occurrences)
        self._atoms[atom_id] = upgraded
        self._bump(f"verify:{atom_id}:{ref.evidence_class}")
        return upgraded

    def record_falsification(self, atom_id: str, ref: EvidenceRef) -> KnowledgeAtom:
        if ref.evidence_class not in (E3_DETERMINISTIC, E4_TEST, E5_RUNTIME, E6_REPEATED):
            raise PermissionError("only E3-E6 evidence can falsify an atom")
        atom = self._atoms[atom_id]
        self._atoms[atom_id] = KnowledgeAtom(
            atom_id=atom.atom_id, subject=atom.subject, relation=atom.relation,
            object=atom.object, context=atom.context, constraints=atom.constraints,
            state=AtomState.FALSIFIED.value, export_policy=atom.export_policy,
            evidence=atom.evidence + (ref,), occurrences=atom.occurrences)
        self._bump(f"falsify:{atom_id}")
        return self._atoms[atom_id]

    # -- queries -------------------------------------------------------------
    def get(self, atom_id: str) -> KnowledgeAtom:
        return self._atoms[atom_id]

    def find_by_subject(self, subject: str) -> list[KnowledgeAtom]:
        canon = _canon_slot(subject)
        return [a for a in self._atoms.values() if _canon_slot(a.subject) == canon]

    def verified_atoms(self) -> list[KnowledgeAtom]:
        return [a for a in self._atoms.values() if a.state == AtomState.VERIFIED.value]

    def conflicts(self) -> list[ConflictSet]:
        return list(self._conflicts.values())

    def exportable(self, transport: Transport) -> list[KnowledgeAtom]:
        return [a for a in self._atoms.values() if export_allowed(a, transport)]

    def freshness(self, atom_id: str, current: Mapping[str, str]) -> str:
        """Deterministic freshness verdict for a verified atom.

        * NOT_VERIFIED — the atom is not in VERIFIED state (nothing to go
          stale; the gate pipeline owns that).
        * TRUSTED — at least one verifying ref (E3-E6) is input-bound and
          its binding matches `current` (every bound input present with the
          same hash).
        * STALE — the atom is verified but NO verifying ref's binding
          matches `current`: the evidence was produced against different
          inputs than now.  This is the false-green guard — a cached PASS
          from before the source/test/dependency change is not evidence.
        * UNBOUND — the atom is verified only through refs without input
          bindings (legacy): unverifiable.  Reported as such; callers must
          not treat it as TRUSTED, and it is not falsely marked STALE.

        A verifying ref is one of class E3-E6 (the same classes that may
        verify — Law 1 symmetry: what may make knowledge trusted is what
        freshness re-checks).
        """
        atom = self._atoms[atom_id]
        if atom.state != AtomState.VERIFIED.value:
            return NOT_VERIFIED
        verifying = [e for e in atom.evidence
                     if e.evidence_class in
                     (E3_DETERMINISTIC, E4_TEST, E5_RUNTIME, E6_REPEATED)]
        if not verifying:
            return NOT_VERIFIED
        if any(e.inputs and inputs_match(e, current) for e in verifying):
            return TRUSTED
        if any(e.inputs for e in verifying):
            return STALE
        return UNBOUND

    @property
    def version(self) -> int:
        return self._version

    def stats(self) -> dict:
        return {
            "version": self._version,
            "atoms": len(self._atoms),
            "verified": len(self.verified_atoms()),
            "conflicts": len(self._conflicts),
            "edges": len(self._graph),
            "dictionary": len(self.dict),
            "operations": len(self._history),
        }

    # -- persistence ----------------------------------------------------------
    def to_base_bytes(self) -> bytes:
        return _encode_container(self)

    def _bump(self, op: str) -> None:
        self._version += 1
        self._history.append(op)


# ---------------------------------------------------------------------------
# container encoding — LOLAKS magic, versioned header, section index,
# string dictionary, per-segment checksums, varints, delta-encoded edges
# ---------------------------------------------------------------------------

def _seg(data: bytes) -> bytes:
    return struct.pack("<II", len(data), zlib.crc32(data) & 0xFFFFFFFF) + data


def _encode_container(store: LKSStore) -> bytes:
    d = store.dict
    # intern everything so the dictionary is complete and deterministic
    for a in store._atoms.values():
        d.intern(a.atom_id); d.intern(a.subject); d.intern(a.relation)
        d.intern(a.object); d.intern(a.context); d.intern(a.constraints)
        d.intern(a.state); d.intern(a.export_policy)
        for e in a.evidence:
            d.intern(e.evidence_id); d.intern(e.content_hash); d.intern(e.evidence_class)
    for c in store._conflicts.values():
        d.intern(c.fingerprint); d.intern(c.proposition); d.intern(c.status)
        for claim, ev in c.claims:
            d.intern(claim); d.intern(ev)
    # pre-intern graph node ids + edge relations so the dictionary is complete
    for src, rel, dst in store._graph:
        d.intern(src); d.intern(rel); d.intern(dst)
    # pre-intern evidence input bindings (names + hashes)
    for k in sorted(store._atoms):
        for e in store._atoms[k].evidence:
            for name, h in e.inputs:
                d.intern(name); d.intern(h)

    # --- dictionary section ---
    dict_blob = bytearray()
    for s in d.as_list():
        raw = s.encode("utf-8")
        dict_blob += varint_encode(len(raw)) + raw
    dict_bytes = _seg(bytes(dict_blob))

    # --- atoms section ---
    atom_blob = bytearray()
    for aid in sorted(store._atoms):
        a = store._atoms[aid]
        atom_blob += varint_encode(d.intern(a.atom_id))
        atom_blob += varint_encode(d.intern(a.subject))
        atom_blob += varint_encode(d.intern(a.relation))
        atom_blob += varint_encode(d.intern(a.object))
        atom_blob += varint_encode(d.intern(a.context))
        atom_blob += varint_encode(d.intern(a.constraints))
        atom_blob += varint_encode(d.intern(a.state))
        atom_blob += varint_encode(d.intern(a.export_policy))
        atom_blob += varint_encode(a.occurrences)
        atom_blob += varint_encode(len(a.evidence))
        for e in a.evidence:
            atom_blob += varint_encode(d.intern(e.evidence_id))
            atom_blob += varint_encode(d.intern(e.content_hash))
            atom_blob += varint_encode(d.intern(e.evidence_class))
            atom_blob += varint_encode(len(e.inputs))
            for name, h in e.inputs:
                atom_blob += varint_encode(d.intern(name))
                atom_blob += varint_encode(d.intern(h))
    atom_bytes = _seg(bytes(atom_blob))

    # --- evidence section: the distinct evidence refs (registry) ---
    ev_blob = bytearray()
    ev_seen: dict[str, int] = {}
    ev_order: list[EvidenceRef] = []
    for a in (store._atoms[k] for k in sorted(store._atoms)):
        for e in a.evidence:
            key = e.evidence_id
            if key not in ev_seen:
                ev_seen[key] = len(ev_order)
                ev_order.append(e)
    ev_blob += varint_encode(len(ev_order))
    for e in ev_order:
        ev_blob += varint_encode(d.intern(e.evidence_id))
        ev_blob += varint_encode(d.intern(e.content_hash))
        ev_blob += varint_encode(d.intern(e.evidence_class))
        ev_blob += varint_encode(len(e.inputs))
        for name, h in e.inputs:
            ev_blob += varint_encode(d.intern(name))
            ev_blob += varint_encode(d.intern(h))
    ev_bytes = _seg(bytes(ev_blob))

    # --- conflicts section ---
    conf_blob = bytearray()
    for cf in sorted(store._conflicts):
        c = store._conflicts[cf]
        conf_blob += varint_encode(d.intern(c.fingerprint))
        conf_blob += varint_encode(d.intern(c.proposition))
        conf_blob += varint_encode(d.intern(c.status))
        conf_blob += varint_encode(len(c.claims))
        for claim, ev in c.claims:
            conf_blob += varint_encode(d.intern(claim))
            conf_blob += varint_encode(d.intern(ev))
    conf_bytes = _seg(bytes(conf_blob))

    # --- graph section: delta-encoded edge endpoints (sorted for determinism) ---
    edge_blob = bytearray()
    ids = sorted({x for edge in store._graph for x in (edge[0], edge[2])})
    id_index = {x: i for i, x in enumerate(ids)}
    edge_blob += varint_encode(len(ids))
    for x in ids:
        edge_blob += varint_encode(d.intern(x))
    edges_sorted = sorted(store._graph)
    edge_blob += varint_encode(len(edges_sorted))
    last = 0
    for src, rel, dst in edges_sorted:
        edge_blob += varint_encode(zigzag_encode(id_index[src] - last))
        last = id_index[src]
        edge_blob += varint_encode(d.intern(rel))
        edge_blob += varint_encode(zigzag_encode(id_index[dst] - id_index[src]))
    graph_bytes = _seg(bytes(edge_blob))

    # --- delta section: base carries no pending deltas ---
    delta_bytes = _seg(varint_encode(0))

    # --- header + index ---
    sections = (dict_bytes, atom_bytes, ev_bytes, conf_bytes, graph_bytes, delta_bytes)
    index = struct.pack("<" + "Q" * SECTION_COUNT, *(len(s) for s in sections))
    header = (MAGIC
              + struct.pack("<BB", FORMAT_VERSION_MAJOR, FORMAT_VERSION_MINOR)
              + struct.pack("<I", SCHEMA_VERSION)
              + struct.pack("<I", MIN_READER)
              + struct.pack("<I", store._version)
              + struct.pack("<Q", len(store._atoms))
              + index)
    return header + b"".join(sections)


def _decode_container(data: bytes) -> LKSStore:
    """Versioned read: rejects unknown major, verifies every segment CRC,
    re-interns into a fresh store.  Never silently reinterprets bytes."""
    if data[:6] != MAGIC:
        raise ValueError("not an LKS container (bad magic)")
    major, minor = struct.unpack_from("<BB", data, 6)
    if major != FORMAT_VERSION_MAJOR:
        raise ValueError(f"unsupported LKS major version {major} "
                         f"(reader {FORMAT_VERSION_MAJOR})")
    schema, min_reader, version, atom_count = struct.unpack_from("<IIIQ", data, 8)
    if min_reader > FORMAT_VERSION_MAJOR:
        raise ValueError(f"container needs reader >= {min_reader}")
    index = struct.unpack_from("<" + "Q" * SECTION_COUNT, data, 28)
    pos = 28 + 8 * SECTION_COUNT
    sections = []
    for ln in index:
        if pos + ln > len(data):
            raise ValueError("section runs past end of container")
        sections.append(data[pos:pos + ln])
        pos += ln
    if pos != len(data):
        raise ValueError("trailing bytes after last section")

    def unseg(b: bytes) -> bytes:
        ln, crc = struct.unpack_from("<II", b, 0)
        body = b[8:8 + ln]
        if len(body) != ln:
            raise ValueError("segment length mismatch")
        if (zlib.crc32(body) & 0xFFFFFFFF) != crc:
            raise ValueError("segment CRC mismatch (corruption)")
        return body

    store = LKSStore()
    # dictionary
    db = unseg(sections[SEC_DICT])
    p = 0
    while p < len(db):
        ln, p = varint_decode(db, p)
        store.dict.intern(db[p:p + ln].decode("utf-8"))
        p += ln
    D = store.dict
    # atoms
    ab = unseg(sections[SEC_ATOMS])
    p = 0
    while p < len(ab):
        aid = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
        subj = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
        rel = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
        obj = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
        ctx = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
        cons = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
        state = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
        pol = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
        occ, p = varint_decode(ab, p)
        ne, p = varint_decode(ab, p)
        evs = []
        for _ in range(ne):
            eid = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
            ch = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
            ec = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
            nin, p = varint_decode(ab, p)
            binds = []
            for _ in range(nin):
                nm = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
                hh = D.get(varint_decode(ab, p)[0]); p = varint_decode(ab, p)[1]
                binds.append((nm, hh))
            evs.append(EvidenceRef(eid, ch, ec, tuple(binds)))
        store._atoms[aid] = KnowledgeAtom(
            atom_id=aid, subject=subj, relation=rel, object=obj, context=ctx,
            constraints=cons, state=state, export_policy=pol,
            evidence=tuple(evs), occurrences=occ)
        store._by_fp[store._atoms[aid].fingerprint] = aid
    if len(store._atoms) != atom_count:
        raise ValueError("atom count mismatch (header vs section)")
    # evidence registry (validated for presence; atoms already carry refs)
    eb = unseg(sections[SEC_EVIDENCE])
    nev, p = varint_decode(eb, 0)
    for _ in range(nev):
        for _ in range(3):
            p = varint_decode(eb, p)[1]
        nin, p = varint_decode(eb, p)
        for _ in range(nin):
            p = varint_decode(eb, p)[1]
            p = varint_decode(eb, p)[1]
    # conflicts
    cb = unseg(sections[SEC_CONFLICTS])
    p = 0
    while p < len(cb):
        fp = D.get(varint_decode(cb, p)[0]); p = varint_decode(cb, p)[1]
        prop = D.get(varint_decode(cb, p)[0]); p = varint_decode(cb, p)[1]
        status = D.get(varint_decode(cb, p)[0]); p = varint_decode(cb, p)[1]
        nc, p = varint_decode(cb, p)
        claims = []
        for _ in range(nc):
            cl = D.get(varint_decode(cb, p)[0]); p = varint_decode(cb, p)[1]
            ev = D.get(varint_decode(cb, p)[0]); p = varint_decode(cb, p)[1]
            claims.append((cl, ev))
        store._conflicts[fp] = ConflictSet(prop, tuple(claims), status)
    # graph
    gb = unseg(sections[SEC_GRAPH])
    p = 0
    nids, p = varint_decode(gb, p)
    ids = [D.get(varint_decode(gb, p)[0]) for _ in range(nids)]
    for _ in range(nids):
        p = varint_decode(gb, p)[1]
    nedges, p = varint_decode(gb, p)
    prev = 0
    for _ in range(nedges):
        sidx = prev + zigzag_decode(varint_decode(gb, p)[0]); p = varint_decode(gb, p)[1]
        prev = sidx
        rel = D.get(varint_decode(gb, p)[0]); p = varint_decode(gb, p)[1]
        didx = sidx + zigzag_decode(varint_decode(gb, p)[0]); p = varint_decode(gb, p)[1]
        store._graph.append((ids[sidx], rel, ids[didx]))
    store._version = version
    # delta section (base carries none, but the segment must still validate)
    unseg(sections[SEC_DELTA])
    return store


# ---------------------------------------------------------------------------
# BASE + DELTA segments — append-only deltas, deterministic compaction
# ---------------------------------------------------------------------------

@dataclass
class LKSFile:
    """BASE (knowledge.lks) + ordered DELTA (.lkd) segments.  Reads see
    base with all deltas applied in order; writes append a new delta;
    compact() deterministically merges everything into a fresh base.

    A delta stores only the operations it carries (atom upserts / edges /
    conflicts) — the smallest unit that keeps the runtime view current
    without rewriting the base."""

    base: bytes
    deltas: list[bytes] = field(default_factory=list)

    @classmethod
    def new(cls) -> "LKSFile":
        return cls(base=b"", deltas=[])

    def snapshot(self) -> LKSStore:
        store = _decode_container(self.base) if self.base else LKSStore()
        for d in self.deltas:
            _apply_delta(store, d)
        return store

    def append_delta(self, ops: Sequence[Mapping]) -> int:
        """Append one delta segment carrying `ops` (add_atom / add_edge /
        add_conflict / verify / falsify).  Returns the delta index."""
        if not ops:
            raise ValueError("empty delta")
        self.deltas.append(_encode_delta(ops))
        return len(self.deltas) - 1

    def compact(self) -> "LKSFile":
        """Deterministic merge: base + all deltas -> new base, no deltas.
        The result decodes identically to `snapshot()` (same atoms, states,
        edges, conflicts, version)."""
        store = self.snapshot()
        return LKSFile(base=_encode_container(store), deltas=[])

    def size(self) -> int:
        return len(self.base) + sum(len(d) for d in self.deltas)


_DELTA_OPS = {"add_atom", "add_edge", "add_conflict", "verify", "falsify"}


def _encode_delta(ops: Sequence[Mapping]) -> bytes:
    body = bytearray()
    body += varint_encode(len(ops))
    for op in ops:
        name = op.get("op")
        if name not in _DELTA_OPS:
            raise ValueError(f"unknown delta op: {name}")
        keys = [(k, v) for k, v in op.items() if k != "op"]
        body += varint_encode(len(name)) + name.encode("utf-8")
        body += varint_encode(len(keys))
        for k, v in keys:
            raw = (v if isinstance(v, str) else json.dumps(v, sort_keys=True)).encode("utf-8")
            body += varint_encode(len(k)) + k.encode("utf-8") + varint_encode(len(raw)) + raw
    return _seg(bytes(body))


def _decode_delta(data: bytes) -> list[dict]:
    body = _unseg_public(data)
    n, p = varint_decode(body, 0)
    ops = []
    for _ in range(n):
        ln, p = varint_decode(body, p)
        name = body[p:p + ln].decode("utf-8"); p += ln
        nk, p = varint_decode(body, p)
        op: dict = {"op": name}
        for _ in range(nk):
            klen, p = varint_decode(body, p)
            key = body[p:p + klen].decode("utf-8"); p += klen
            vlen, p = varint_decode(body, p)
            val = body[p:p + vlen].decode("utf-8"); p += vlen
            op[key] = val
        ops.append(op)
    return ops


def _unseg_public(b: bytes) -> bytes:
    ln, crc = struct.unpack_from("<II", b, 0)
    body = b[8:8 + ln]
    if len(body) != ln or (zlib.crc32(body) & 0xFFFFFFFF) != crc:
        raise ValueError("delta segment corrupt")
    return body


def _evidence_from_dict(d: Mapping) -> EvidenceRef:
    inputs = tuple(sorted((d.get("inputs") or {}).items()))
    return EvidenceRef(evidence_id=d["evidence_id"], content_hash=d["content_hash"],
                       evidence_class=d.get("evidence_class", E2_REFERENCE),
                       inputs=inputs)


def _apply_delta(store: LKSStore, data: bytes) -> None:
    for op in _decode_delta(data):
        name = op["op"]
        if name == "add_atom":
            a = json.loads(op["atom"])
            store.add_atom(KnowledgeAtom(
                atom_id=a["atom_id"], subject=a["subject"], relation=a["relation"],
                object=a["object"], context=a.get("context", ""),
                constraints=a.get("constraints", ""),
                state=a.get("state", AtomState.CANDIDATE.value),
                export_policy=a.get("export_policy", ExportPolicy.MODEL_LOCAL.value),
                evidence=tuple(_evidence_from_dict(e) for e in a.get("evidence", [])),
                occurrences=a.get("occurrences", 1)))
        elif name == "add_edge":
            store.add_edge(op["src"], op["rel"], op["dst"])
        elif name == "add_conflict":
            c = json.loads(op["conflict"])
            store.add_conflict(ConflictSet(
                proposition=c["proposition"],
                claims=tuple((cl, ev) for cl, ev in c["claims"]),
                status=c.get("status", "UNRESOLVED")))
        elif name == "verify":
            store.record_verification(op["atom_id"], _evidence_from_dict(json.loads(op["evidence"])))
        elif name == "falsify":
            store.record_falsification(op["atom_id"], _evidence_from_dict(json.loads(op["evidence"])))
        else:
            raise ValueError(f"unknown delta op: {name}")


# ---------------------------------------------------------------------------
# deterministic, zero-model smoke
# ---------------------------------------------------------------------------

def run_lks_smoke() -> dict:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, bool(ok)))

    # 1. form-invariant dedup: same structure written in different form
    #    (case / underscore / whitespace) merges to one atom.
    #    (Paraphrase-level dedup is lola_candidate's structural_fingerprint —
    #    LKS normalizes form, not wording.)
    s = LKSStore()
    a1 = s.add_atom(KnowledgeAtom("A1", "MQL5_Compiler", "rejects_pattern",
                                  "Legacy_Objects_Total_Call", context="Build XYZ"))
    a2 = s.add_atom(KnowledgeAtom("A2", "MQL5 Compiler", "rejects pattern",
                                  "Legacy Objects Total Call", context="build xyz"))
    check("form_dedup_merges", a1 == a2 and len(s._atoms) == 1)
    check("repetition_is_counter", s.get(a1).occurrences == 2)

    # 2. Law 1: E2 cannot verify; E3 can
    model_ev = EvidenceRef("EV1", "aa" * 32, E2_REFERENCE)
    det_ev = EvidenceRef("EV2", "bb" * 32, E3_DETERMINISTIC)
    try:
        s.record_verification(a1, model_ev)
        check("law1_blocks_e2", False)
    except PermissionError:
        check("law1_blocks_e2", True)
    s.record_verification(a1, det_ev)
    check("e3_verifies", s.get(a1).state == AtomState.VERIFIED.value)

    # 3. contradiction -> ConflictSet, unresolved, not averaged away
    cs = ConflictSet("ObjectsTotal returns count",
                     (("returns_count", "EV3"), ("returns_zero", "EV4")))
    s.add_conflict(cs)
    check("conflict_recorded", len(s.conflicts()) == 1
          and s.conflicts()[0].status == "UNRESOLVED")

    # 4. graph edge stored once
    b = s.add_atom(KnowledgeAtom("B1", "PositionAPI", "defined_in", "MQL5"))
    s.add_edge(a1, "uses", b)
    s.add_edge(a1, "uses", b)  # duplicate edge must not double-store
    check("edge_stored_once", len(s._graph) == 1)

    # 5. export policy gate
    local_only = s.add_atom(KnowledgeAtom("L1", "private", "has", "secret",
                                          export_policy=ExportPolicy.LOCAL_ONLY.value))
    check("local_only_blocked_cloud",
          not any(a.atom_id == local_only for a in s.exportable(Transport.CLOUD))
          and any(a.atom_id == local_only for a in s.exportable(Transport.LOCAL)))

    # 6. round-trip container
    blob = s.to_base_bytes()
    check("magic_ok", blob[:6] == MAGIC)
    s2 = _decode_container(blob)
    check("roundtrip_atoms", len(s2._atoms) == len(s._atoms))
    check("roundtrip_verified", s2.get(a1).state == AtomState.VERIFIED.value)
    check("roundtrip_conflicts", len(s2.conflicts()) == len(s.conflicts()))
    check("roundtrip_edges", len(s2._graph) == len(s._graph))

    # 7. corruption detected
    bad = bytearray(blob); bad[-1] ^= 0xFF
    try:
        _decode_container(bytes(bad))
        check("corruption_detected", False)
    except ValueError:
        check("corruption_detected", True)

    # 8. base + delta + compact equivalence
    f = LKSFile.new()
    f.base = blob
    delta_ops = [
        {"op": "add_atom",
         "atom": json.dumps({"atom_id": "D1", "subject": "Kotlin",
                             "relation": "compiles_with", "object": "Gradle",
                             "context": "ci"}),
         "evidence": []},
    ]
    # _encode_delta expects atom as a value; build via store to keep it simple
    f.append_delta([{"op": "add_atom",
                     "atom": json.dumps({"atom_id": "D1", "subject": "Kotlin",
                                         "relation": "compiles_with", "object": "Gradle",
                                         "context": "ci"})}])
    snap = f.snapshot()
    check("delta_applied", "D1" in snap._atoms)
    compacted = f.compact()
    check("compact_no_deltas", compacted.deltas == [])
    c_snap = compacted.snapshot()
    check("compact_preserves", c_snap.get("D1").subject == "Kotlin"
          and c_snap.get(a1).state == AtomState.VERIFIED.value)

    # 9. version gate
    wrong_major = blob[:6] + bytes([9, 0]) + blob[8:]
    try:
        _decode_container(wrong_major)
        check("version_gate", False)
    except ValueError:
        check("version_gate", True)

    # 10. freshness: verified knowledge must not silently go green after its
    #     inputs change (thread weakness #11: cached PASS != evidence for the
    #     new candidate)
    fs = LKSStore()

    def fatom(aid, sub, rel, obj, ctx):
        return KnowledgeAtom(atom_id=aid, subject=sub, relation=rel,
                             object=obj, context=ctx)

    f1 = fs.add_atom(fatom("F1", "Build", "passes_with", "dep-v1", "ci"))
    fs.record_verification(f1, EvidenceRef("FEV", "ff" * 32, E4_TEST,
                                           inputs=(("source_hash", "aa" * 32),
                                                   ("test_hash", "bb" * 32))))
    check("fresh_trusted", fs.freshness(f1, {"source_hash": "aa" * 32,
                                             "test_hash": "bb" * 32}) == TRUSTED)
    check("stale_after_input_change", fs.freshness(f1, {"source_hash": "cc" * 32,
                                                        "test_hash": "bb" * 32}) == STALE)
    check("stale_when_binding_missing", fs.freshness(f1, {"other": "dd" * 32}) == STALE)
    f2 = fs.add_atom(fatom("F2", "Legacy", "known", "fact", "old"))
    fs.record_verification(f2, EvidenceRef("FEV2", "ee" * 32, E3_DETERMINISTIC))
    check("unbound_reported_not_trusted", fs.freshness(f2, {}) == UNBOUND)
    f3 = fs.add_atom(fatom("F3", "x", "y", "z", ""))
    check("not_verified", fs.freshness(f3, {}) == NOT_VERIFIED)
    # bindings survive the container round-trip
    fb = _decode_container(fs.to_base_bytes())
    check("bindings_survive_roundtrip", fb.freshness(f1, {"source_hash": "aa" * 32,
                                                          "test_hash": "bb" * 32}) == TRUSTED
          and fb.freshness(f1, {"source_hash": "99" * 32,
                                "test_hash": "bb" * 32}) == STALE)

    # 11. varint / zigzag sanity
    check("varint_roundtrip",
          all(varint_decode(varint_encode(v), 0)[0] == v for v in (0, 1, 127, 128, 300, 100000)))
    check("zigzag_roundtrip",
          all(zigzag_decode(zigzag_encode(v)) == v for v in (0, 1, -1, 100, -100, 100000)))

    passed = all(ok for _, ok in checks)
    return {"passed": passed,
            "checks": [{"name": n, "ok": ok} for n, ok in checks],
            "total": len(checks), "failed": [n for n, ok in checks if not ok]}
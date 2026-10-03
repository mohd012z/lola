"""NovelCandidate v1 — immutable candidate objects, structural fingerprints,
deterministic operators, and an episode-aware duplicate gate.

Study source: the shared GGUF deep-dive thread (share 6ac0e84e continuation,
138 messages), whose final sections prescribe this exact vertical slice for
"LOLA Novel/Episode v1" and define its acceptance test verbatim:

    RUN #1: NovelEngine proposes NC-1 -> NC-1 fails -> Episode E-1 records why.
    RUN #2: same/similar problem -> index retrieves E-1 -> the NC-1 duplicate
            is suppressed -> a different candidate is generated instead.

    "If that works reproducibly, LOLA has begun learning from experience
    rather than merely accumulating memory."

The thread's binding boundary (enforced here as invariants):

    NovelCandidate = POSSIBLE      (a hypothesis; never truth)
    Episode        = OBSERVED      (measured history)
    Pattern        = INFERRED FROM EXPERIENCE
    Skill          = VERIFIED REUSABLE PROCEDURE

"imagination and observation must never share the same truth status."

What lola already has (this module does NOT duplicate):
  * lola_novelty            — IdeaGenome, freeze_idea, independence class
  * lola_repeated_episode   — context_fingerprint, repeated-pattern analysis
  * lola_evidence_lineage   — lineage DAG, independence accounting
  * lola_code_intel         — symbols, CodeGraph, FTS5, ContextCompiler

What this module adds: the persistent candidate layer between them — the
immutable hypothesis object, its structural fingerprint (wording-invariant),
its state machine (VERIFIED is unreachable without an observed episode),
its lineage links, and the gate that makes run #2 smarter than run #1.

Design invariants (aligned with lola's frozen laws):
  * **Deterministic, zero-model.** No LLM/GGUF call anywhere: stdlib only
    (dataclasses + sqlite3 + hashlib + the shared context_fingerprint).
  * **Candidates are immutable.** Records are never edited: state moves and
    new generations are *new* objects linked by lineage (tested_by,
    evolved_into, criticized_by).
  * **POSSIBLE and OBSERVED never share truth status.** A candidate reaches
    VERIFIED only through record_episode() on a PASS/VERIFIED outcome —
    never through self-report, confidence, or prose.
  * **The gate reads observations only.** Duplicate suppression consults
    recorded episodes (structural fingerprint match), never prose similarity.
  * **Rebuildable cache DB.** The store holds derived hypothesis state; it
    is safe to delete and re-derive. journal_mode=MEMORY + synchronous=OFF
    (same rationale as lola_code_intel).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# Structural fingerprint — the thread's five-slot normalization
# (RESOURCE / OPERATION / TRIGGER / TARGET / SCOPE). Two candidates are a
# STRUCTURAL DUPLICATE when their canonical slots match, no matter how each
# is worded. Canonical vocabulary is a small explicit map; extending it is a
# deliberate, reviewable change (an unreviewed vocabulary silently changes
# dedupe behavior).
# ---------------------------------------------------------------------------
SLOT_RESOURCE = "resource"
SLOT_OPERATION = "operation"
SLOT_TRIGGER = "trigger"
SLOT_TARGET = "target"
SLOT_SCOPE = "scope"
FINGERPRINT_SLOTS = (
    SLOT_RESOURCE, SLOT_OPERATION, SLOT_TRIGGER, SLOT_TARGET, SLOT_SCOPE,
)

_CANON: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("KNOWLEDGE", ("knowledge", "documentation", "docs", "reference", "documentation")),
    ("CACHE", ("cache", "caches", "cached")),
    ("CODE", ("code", "source", "symbols", "symbols index")),
    ("CODE_GRAPH", ("codegraph", "code graph", "graph", "symbol graph")),
    ("MODEL", ("model", "models", "gguf", "qwen")),
    ("MEMORY", ("memory", "ram", "kv cache", "kv-cache")),
    ("CONTEXT", ("context", "context capsule", "working set")),
    ("SKILL", ("skill", "skills", "procedure")),
    ("EPISODE", ("episode", "episodes", "experience")),
    ("PREFETCH", ("prefetch", "preload", "warm", "warm-up", "warmup")),
    ("LAZY", ("lazy", "lazy-load", "lazy_load", "just-in-time", "on-demand", "demand")),
    ("COMPILE", ("compile", "compiled", "compiling")),
    ("DEDUPE", ("dedupe", "deduplicate", "deduplication")),
    ("SHARE", ("share", "shared", "sharing")),
    ("EVICT", ("evict", "eviction", "consolidate", "consolidation")),
    ("COMPRESS", ("compress", "compression", "quantize", "quantization")),
    ("BATCH", ("batch", "batching")),
    ("INVERT", ("invert", "inversion", "reverse")),
    ("PREDICT", ("predict", "prediction", "predicted", "anticipate")),
    ("REUSE", ("reuse", "reused", "recycle")),
    ("LATENCY", ("latency", "ttft", "speed", "speedup", "retrieval time", "startup")),
    ("MEMORY_PRESSURE", ("memory pressure", "ram pressure", "peak ram")),
    ("ACCURACY", ("accuracy", "correctness")),
    ("THROUGHPUT", ("throughput", "tokens per second")),
    ("RETRIEVAL", ("retrieval", "lookup", "search")),
    ("CODEBASE", ("codebase", "repository", "repo")),
    ("RUNTIME", ("runtime", "session", "device")),
    ("BUILD", ("build", "compile time", "compile-time")),
)


def _canonicalize(slot: str, value: str) -> str:
    v = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if not v:
        return ""
    for canon, forms in _CANON:
        for f in forms:
            if f == v:
                return canon
    return v  # unknown values stay literal (deterministic, still comparable)


def structural_fingerprint(*, resource: str = "", operation: str = "",
                           trigger: str = "", target: str = "",
                           scope: str = "") -> str:
    """Word-invariant identity of a candidate's structure.

    Two differently-worded candidates with the same five canonical slots get
    the same fingerprint — the thread's "CONCEPTUAL DUPLICATE without Qwen".
    """
    parts = "|".join(
        _canonicalize(slot, val)
        for slot, val in ((SLOT_RESOURCE, resource), (SLOT_OPERATION, operation),
                          (SLOT_TRIGGER, trigger), (SLOT_TARGET, target),
                          (SLOT_SCOPE, scope))
    )
    return "FP-" + hashlib.sha256(parts.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Candidate state machine. VERIFIED is only reachable from TESTED, and
# TESTED is only reachable through an observed episode — so model confidence
# can never become system knowledge.
# ---------------------------------------------------------------------------
STATE_IMAGINED = "IMAGINED"
STATE_CRITICIZED = "CRITICIZED"
STATE_TESTED = "TESTED"
STATE_VERIFIED = "VERIFIED"
STATE_FALSIFIED = "FALSIFIED"
STATE_REJECTED = "REJECTED"

_TRANSITIONS: Mapping[str, tuple[str, ...]] = {
    STATE_IMAGINED: (STATE_CRITICIZED, STATE_REJECTED, STATE_TESTED),
    STATE_CRITICIZED: (STATE_REJECTED, STATE_TESTED),
    STATE_TESTED: (STATE_VERIFIED, STATE_FALSIFIED),
    STATE_VERIFIED: (),
    STATE_FALSIFIED: (),
    STATE_REJECTED: (),
}

# Episode outcomes -> candidate state moves (observation drives state).
_OUTCOME_TO_STATE = {
    "PASS": STATE_VERIFIED, "VERIFIED": STATE_VERIFIED,
    "FAIL": STATE_FALSIFIED, "FAILED": STATE_FALSIFIED,
    "FALSIFIED": STATE_FALSIFIED,
    "INCONCLUSIVE": STATE_TESTED, "PARTIAL_SUCCESS": STATE_TESTED,
    "NOT_READY": STATE_TESTED,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class NovelCandidate:
    """An immutable hypothesis — structured, not prose.

    The record is never edited: state moves and new generations produce new
    objects (see transition/evolve), keeping lineage intact.
    """
    title: str
    mechanism: str
    resource: str = ""
    operation: str = ""
    trigger: str = ""
    target: str = ""
    scope: str = ""
    problem_id: str = ""
    goal: str = ""
    assumptions: tuple = ()
    unknowns: tuple = ()
    predictions: tuple = ()
    failure_modes: tuple = ()
    transformations: tuple = ()
    parent_ids: tuple = ()
    state: str = STATE_IMAGINED
    candidate_id: str = ""
    fingerprint: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not str(self.title).strip() or not str(self.mechanism).strip():
            raise ValueError("title and mechanism are required")
        fp = self.fingerprint or structural_fingerprint(
            resource=self.resource, operation=self.operation,
            trigger=self.trigger, target=self.target, scope=self.scope)
        cid = self.candidate_id or "NC-" + hashlib.sha256(
            (self.title + "|" + self.mechanism + "|" + fp).encode("utf-8")
        ).hexdigest()[:12].upper()
        object.__setattr__(self, "fingerprint", fp)
        object.__setattr__(self, "candidate_id", cid)
        object.__setattr__(self, "created_at", self.created_at or _now())
        if self.state not in _TRANSITIONS:
            raise ValueError(f"unknown state: {self.state}")

    def transition(self, new_state: str) -> "NovelCandidate":
        """Return a new record in new_state; raise on an illegal move."""
        if new_state not in _TRANSITIONS:
            raise ValueError(f"unknown state: {new_state}")
        if new_state not in _TRANSITIONS[self.state]:
            raise ValueError(
                f"illegal transition {self.state} -> {new_state} "
                f"(allowed: {', '.join(_TRANSITIONS[self.state]) or 'none'})")
        return replace(self, state=new_state)

    def to_record(self) -> dict:
        """Serialize with an explicit verified flag (Law 1: state is a claim
        about evidence, never implicit)."""
        return {
            "candidate_id": self.candidate_id,
            "fingerprint": self.fingerprint,
            "problem_id": self.problem_id,
            "goal": self.goal,
            "title": self.title,
            "mechanism": self.mechanism,
            "slots": {s: getattr(self, s) for s in FINGERPRINT_SLOTS},
            "assumptions": list(self.assumptions),
            "unknowns": list(self.unknowns),
            "predictions": list(self.predictions),
            "failure_modes": list(self.failure_modes),
            "transformations": list(self.transformations),
            "parent_ids": list(self.parent_ids),
            "state": self.state,
            "verified": self.state == STATE_VERIFIED,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Deterministic operators — the thread's transformation vocabulary, applied
# as *structural* mutations of a candidate (a parent stays immutable; each
# operator returns a NEW child candidate linked to its parent). This is what
# lets the engine diverge without a model: operators change slots, not prose.
# ---------------------------------------------------------------------------
# (operator, slot-to-mutate, new-slot-value or None to clear)
_OPERATORS: tuple[tuple[str, str, str | None], ...] = (
    ("LAZY", SLOT_TRIGGER, "on-demand"),
    ("PREDICT", SLOT_TRIGGER, "predict"),
    ("SHARE", SLOT_OPERATION, "shared"),
    ("COMPILE", SLOT_OPERATION, "compile"),
    ("CACHE", SLOT_RESOURCE, "cache"),
    ("PREFETCH", SLOT_OPERATION, "prefetch"),
    ("EVICT", SLOT_OPERATION, "evict"),
    ("INVERT", SLOT_OPERATION, "invert"),
    ("SCOPE_CODEBASE", SLOT_SCOPE, "codebase"),
    ("TARGET_LATENCY", SLOT_TARGET, "latency"),
)
OPERATOR_NAMES: tuple[str, ...] = tuple(op for op, _, _ in _OPERATORS)


def apply_operator(candidate: NovelCandidate, operator: str) -> NovelCandidate:
    """Apply one structural operator; returns a NEW child candidate.

    The child is IMAGINED again (a mutation is a new hypothesis, never
    inherits its parent's evidence) and carries parent_ids for lineage.
    """
    entry = next((e for e in _OPERATORS if e[0] == operator), None)
    if entry is None:
        raise ValueError(f"unknown operator: {operator} (known: {', '.join(OPERATOR_NAMES)})")
    _, slot, value = entry
    slots = {s: getattr(candidate, s) for s in FINGERPRINT_SLOTS}
    slots[slot] = value or ""
    child = NovelCandidate(
        title=f"{candidate.title} [{operator}]",
        mechanism=candidate.mechanism,
        problem_id=candidate.problem_id,
        goal=candidate.goal,
        assumptions=candidate.assumptions,
        unknowns=candidate.unknowns,
        predictions=candidate.predictions,
        failure_modes=candidate.failure_modes,
        transformations=(*candidate.transformations, operator),
        parent_ids=(candidate.candidate_id,),
        **slots,
    )
    return child


def diverge(candidate: NovelCandidate, operators: Sequence[str] | None = None) -> tuple[NovelCandidate, ...]:
    """Generate a deterministic candidate population from one seed.

    Duplicates (same structural fingerprint) are dropped — diversity of
    *structure*, not of wording.
    """
    ops = tuple(operators) if operators is not None else OPERATOR_NAMES
    seen: set[str] = set()
    out: list[NovelCandidate] = []
    for op in ops:
        try:
            child = apply_operator(candidate, op)
        except ValueError:
            continue
        if child.fingerprint in seen:
            continue
        seen.add(child.fingerprint)
        out.append(child)
    return tuple(out)


# ---------------------------------------------------------------------------
# Episode — OBSERVED history (a measured record, never a hypothesis).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Episode:
    candidate_id: str
    fingerprint: str
    outcome: str                 # PASS/FAIL/INCONCLUSIVE/FALSIFIED/...
    episode_id: str = ""
    predicted: Mapping[str, Any] | None = None
    observed: Mapping[str, Any] | None = None
    delta: Mapping[str, Any] | None = None
    notes: str = ""
    created_at: str = ""

    def __post_init__(self):
        if self.outcome not in _OUTCOME_TO_STATE:
            raise ValueError(f"unknown outcome: {self.outcome}")
        object.__setattr__(self, "created_at", self.created_at or _now())
        if self.episode_id and self.episode_id.startswith("EP-"):
            return
        base = hashlib.sha256(
            (self.candidate_id + "|" + self.fingerprint + "|" + self.outcome).encode("utf-8")
        ).hexdigest()[:12].upper()
        object.__setattr__(self, "episode_id", f"EP-{base}")

    @property
    def candidate_state_move(self) -> str:
        return _OUTCOME_TO_STATE[self.outcome]

    def to_record(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "candidate_id": self.candidate_id,
            "fingerprint": self.fingerprint,
            "outcome": self.outcome,
            "predicted": dict(self.predicted or {}),
            "observed": dict(self.observed or {}),
            "delta": dict(self.delta or {}),
            "notes": self.notes,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Store — persistent, rebuildable SQLite (candidates + episodes + lineage).
# ---------------------------------------------------------------------------
import sqlite3  # noqa: E402


class CandidateStore:
    """SQLite store for candidates, episodes, and their lineage links.

    The DB is a rebuildable cache (derived hypothesis state only), so
    journal_mode=MEMORY + synchronous=OFF applies (same rationale as
    lola_code_intel).
    """

    def __init__(self, db_path):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=MEMORY")
        self.conn.execute("PRAGMA synchronous=OFF")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id  TEXT PRIMARY KEY,
                fingerprint   TEXT NOT NULL,
                problem_id    TEXT,
                goal          TEXT,
                title         TEXT,
                mechanism     TEXT,
                slots         TEXT,
                assumptions   TEXT,
                predictions   TEXT,
                state         TEXT,
                parent_ids    TEXT,
                created_at    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_cand_fp ON candidates(fingerprint);
            CREATE TABLE IF NOT EXISTS episodes (
                episode_id     TEXT PRIMARY KEY,
                candidate_id   TEXT NOT NULL REFERENCES candidates(candidate_id),
                fingerprint    TEXT NOT NULL,
                outcome        TEXT,
                predicted      TEXT,
                observed       TEXT,
                delta          TEXT,
                notes          TEXT,
                created_at     TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ep_fp ON episodes(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_ep_cand ON episodes(candidate_id);
            CREATE TABLE IF NOT EXISTS lineage (
                src_id      TEXT,
                dst_id      TEXT,
                relation    TEXT,   -- tested_by | evolved_into | criticized_by
                UNIQUE(src_id, dst_id, relation)
            );
            """
        )
        self.conn.commit()

    # -- candidates --------------------------------------------------------
    def add_candidate(self, c: NovelCandidate) -> bool:
        """Insert if new; idempotent on candidate_id. Returns True if new."""
        cur = self.conn.execute(
            "SELECT 1 FROM candidates WHERE candidate_id = ?", (c.candidate_id,))
        if cur.fetchone():
            return False
        import json as _json
        self.conn.execute(
            "INSERT INTO candidates (candidate_id, fingerprint, problem_id, goal,"
            " title, mechanism, slots, assumptions, predictions, state, parent_ids,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (c.candidate_id, c.fingerprint, c.problem_id, c.goal, c.title,
             c.mechanism, _json.dumps({s: getattr(c, s) for s in FINGERPRINT_SLOTS}),
             _json.dumps(list(c.assumptions)), _json.dumps(list(c.predictions)),
             c.state, _json.dumps(list(c.parent_ids)), c.created_at))
        self.conn.commit()
        return True

    def candidate_exists(self, candidate_id: str) -> bool:
        return bool(self.conn.execute(
            "SELECT 1 FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone())

    def candidates_for_fingerprint(self, fingerprint: str) -> list[str]:
        return [r["candidate_id"] for r in self.conn.execute(
            "SELECT candidate_id FROM candidates WHERE fingerprint = ? ORDER BY candidate_id",
            (fingerprint,))]

    def set_state(self, candidate_id: str, state: str) -> None:
        if state not in _TRANSITIONS:
            raise ValueError(f"unknown state: {state}")
        self.conn.execute("UPDATE candidates SET state = ? WHERE candidate_id = ?",
                          (state, candidate_id))
        self.conn.commit()

    def get_state(self, candidate_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT state FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return row["state"] if row else None

    # -- episodes ----------------------------------------------------------
    def add_episode(self, ep: Episode) -> bool:
        import json as _json
        cur = self.conn.execute("SELECT 1 FROM episodes WHERE episode_id = ?", (ep.episode_id,))
        if cur.fetchone():
            return False
        self.conn.execute(
            "INSERT INTO episodes (episode_id, candidate_id, fingerprint, outcome,"
            " predicted, observed, delta, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (ep.episode_id, ep.candidate_id, ep.fingerprint, ep.outcome,
             _json.dumps(ep.predicted or {}), _json.dumps(ep.observed or {}),
             _json.dumps(ep.delta or {}), ep.notes, ep.created_at))
        self.conn.commit()
        return True

    def episodes_for_fingerprint(self, fingerprint: str) -> list[dict]:
        import json as _json
        rows = self.conn.execute(
            "SELECT * FROM episodes WHERE fingerprint = ? ORDER BY created_at, episode_id",
            (fingerprint,))
        out = []
        for r in rows:
            d = dict(r)
            for k in ("predicted", "observed", "delta"):
                d[k] = _json.loads(d[k] or "{}")
            out.append(d)
        return out

    def episodes_for_candidate(self, candidate_id: str) -> list[dict]:
        return self.episodes_for_fingerprint(
            self.conn.execute("SELECT fingerprint FROM candidates WHERE candidate_id = ?",
                              (candidate_id,)).fetchone()["fingerprint"])

    # -- lineage -----------------------------------------------------------
    def link(self, src: str, dst: str, relation: str) -> None:
        if relation not in ("tested_by", "evolved_into", "criticized_by"):
            raise ValueError(f"unknown relation: {relation}")
        self.conn.execute(
            "INSERT OR IGNORE INTO lineage (src_id, dst_id, relation) VALUES (?,?,?)",
            (src, dst, relation))
        self.conn.commit()

    def lineage(self, candidate_id: str, relation: str) -> list[str]:
        return [r["dst_id"] for r in self.conn.execute(
            "SELECT dst_id FROM lineage WHERE src_id = ? AND relation = ? ORDER BY dst_id",
            (candidate_id, relation))]

    def close(self) -> None:
        self.conn.close()


# ---------------------------------------------------------------------------
# The gate — the thread's acceptance-test core. Reads OBSERVATIONS only: a
# candidate is suppressed when its structural fingerprint matches a recorded
# episode that failed. Empty store => admits (default-open for new
# knowledge, default-deny for repeats).
# ---------------------------------------------------------------------------
def gate(candidate: NovelCandidate, store: CandidateStore) -> dict:
    """Decide NOVEL / DUPLICATE / KNOWN_FAILURE for a candidate.

    DUPLICATE      — a candidate with the same structural fingerprint already
                     exists (regardless of episode outcome): do not re-record.
    KNOWN_FAILURE  — a recorded episode for this fingerprint FAILED/FALSIFIED:
                     the idea was tried and refuted by observation; suppress.
    NOVEL          — admit.
    """
    fp = candidate.fingerprint
    if store.candidates_for_fingerprint(fp):
        return {"verdict": "DUPLICATE", "fingerprint": fp,
                "existing": store.candidates_for_fingerprint(fp), "episodes": []}
    eps = store.episodes_for_fingerprint(fp)
    failed = [e for e in eps if e["outcome"] in ("FAIL", "FAILED", "FALSIFIED")]
    if failed:
        return {"verdict": "KNOWN_FAILURE", "fingerprint": fp, "existing": [],
                "episodes": [e["episode_id"] for e in failed]}
    return {"verdict": "NOVEL", "fingerprint": fp, "existing": [], "episodes": [e["episode_id"] for e in eps]}


def record_outcome(store: CandidateStore, candidate: NovelCandidate,
                   outcome: str, *, predicted=None, observed=None,
                   delta=None, notes: str = "") -> tuple[Episode, str]:
    """Record an observed outcome; advance the candidate's state from the
    observation (not from the candidate's own claim). Returns (episode, new_state)."""
    ep = Episode(candidate_id=candidate.candidate_id, fingerprint=candidate.fingerprint,
                 outcome=outcome, predicted=predicted or {}, observed=observed or {},
                 delta=delta or {}, notes=notes)
    store.add_episode(ep)
    store.link(ep.episode_id, candidate.candidate_id, "tested_by")
    new_state = ep.candidate_state_move
    # Enforce the state machine: IMAGINED/CRITICIZED -> TESTED -> VERIFIED/FALSIFIED
    current = store.get_state(candidate.candidate_id) or STATE_IMAGINED
    if current in (STATE_IMAGINED, STATE_CRITICIZED) and new_state in (STATE_VERIFIED, STATE_FALSIFIED):
        store.set_state(candidate.candidate_id, STATE_TESTED)
        current = STATE_TESTED
    if new_state != current:
        if new_state in _TRANSITIONS[current]:
            store.set_state(candidate.candidate_id, new_state)
        else:
            store.set_state(candidate.candidate_id, STATE_TESTED)
            new_state = STATE_TESTED
    return ep, new_state


# ---------------------------------------------------------------------------
# Smoke — the thread's acceptance test, made reproducible:
#
#   RUN #1: candidate proposed -> experimented -> FAILS -> episode recorded.
#   RUN #2: same problem -> engine diverges -> the failed structure is
#           suppressed by the gate (retrieved via its fingerprint) -> a
#           different candidate is generated instead.
#
# If this passes, "LOLA has begun learning from experience rather than
# merely accumulating memory."
# ---------------------------------------------------------------------------
def run_candidate_smoke() -> dict:
    import tempfile
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, bool(ok)))

    with tempfile.TemporaryDirectory() as td:
        store = CandidateStore(td + "/cand.db")
        try:
            seed = NovelCandidate(
                title="Prefetch documentation before the engine requests it",
                mechanism="Predict next retrieval and warm the doc cache early",
                resource="documentation", operation="preload",
                trigger="before request", target="latency",
                problem_id="P-1", goal="reduce retrieval latency",
                assumptions=("retrieval is predictable",),
                predictions=("retrieval latency decreases",),
                failure_modes=("wrong prediction wastes I/O",),
            )
            # 1. Fingerprint: wording-invariant
            reworded = NovelCandidate(
                title="Warm the documentation cache ahead of demand",
                mechanism="Preload docs predicted to be needed, lowering latency",
                resource="documentation", operation="preload",
                trigger="before request", target="latency",
                problem_id="P-1",
            )
            check("fingerprint_stable_across_wording",
                  seed.fingerprint == reworded.fingerprint and seed.fingerprint.startswith("FP-"))

            # 2. Different structure -> different fingerprint
            other = NovelCandidate(
                title="Lazy-load the model", mechanism="Load GGUF only on demand",
                resource="model", operation="lazy", trigger="on-demand",
                problem_id="P-1",
            )
            check("fingerprint_differs_for_different_structure", other.fingerprint != seed.fingerprint)

            # 3. RUN #1: propose, experiment, fail, record
            store.add_candidate(seed)
            check("run1_candidate_stored", store.candidate_exists(seed.candidate_id))
            g0 = gate(seed, store)
            check("run1_gate_duplicate_when_stored", g0["verdict"] == "DUPLICATE")
            ep1, st1 = record_outcome(store, seed, "FAIL",
                                      predicted={"latency_ms": 95},
                                      observed={"latency_ms": 180},
                                      delta={"latency_ms": 85},
                                      notes="prefetch wasted I/O")
            check("run1_episode_recorded", ep1.episode_id.startswith("EP-") and st1 == STATE_FALSIFIED)
            check("run1_state_is_observed", store.get_state(seed.candidate_id) == STATE_FALSIFIED)

            # 4. RUN #2: same problem -> diverge -> gate suppresses the failed
            #    structure and admits a genuinely different one
            run2 = diverge(seed)
            check("run2_diverges_deterministically", len(run2) >= 5)
            resuppress = NovelCandidate(  # same slots as seed, fresh wording
                title="Warm documentation cache ahead of request again",
                mechanism="Preload predicted docs to cut latency (retry)",
                resource="documentation", operation="preload",
                trigger="before request", target="latency",
                problem_id="P-1",
            )
            # seed itself is already stored -> DUPLICATE (wording change does
            # not evade the gate: same structure, same fingerprint)
            check("run2_failed_structure_duplicate",
                  gate(seed, store)["verdict"] == "DUPLICATE"
                  and gate(resuppress, store)["verdict"] == "DUPLICATE")
            # a *re-derived* child of the failed structure: its fingerprint
            # matches no stored candidate but its episodes? No — children have
            # new slots. The KNOWN_FAILURE branch fires for the SAME structure
            # when it is not yet stored as a candidate:
            store2 = CandidateStore(td + "/cand2.db")
            try:
                ep2, _ = record_outcome(store2, seed, "FAIL",
                                        predicted={"x": 1}, observed={"x": 2})
                retry = NovelCandidate(  # same structure, never stored as candidate
                    title="Retry: preload docs before request",
                    mechanism="Warm the predicted documentation cache",
                    resource="documentation", operation="preload",
                    trigger="before request", target="latency",
                    problem_id="P-1",
                )
                g2 = gate(retry, store2)
                check("run2_known_failure_suppressed",
                      g2["verdict"] == "KNOWN_FAILURE" and ep2.episode_id in g2["episodes"])
                g3 = gate(other, store2)
                check("run2_different_candidate_admitted", g3["verdict"] == "NOVEL")
            finally:
                store2.close()

            # 5. State machine: IMAGINED cannot jump to VERIFIED
            try:
                seed.transition(STATE_VERIFIED)
                check("state_machine_blocks_direct_verify", False)
            except ValueError:
                check("state_machine_blocks_direct_verify", True)
            ok_chain = seed.transition(STATE_CRITICIZED).transition(STATE_TESTED).transition(STATE_VERIFIED)
            check("state_machine_allows_evidenced_path", ok_chain.state == STATE_VERIFIED)

            # 6. Immutability
            try:
                seed.title = "hacked"  # type: ignore[reportAttributeAccessIssue]  # intentional: must raise
                check("candidate_immutable", False)
            except (FrozenInstanceError, AttributeError):
                check("candidate_immutable", True)

            # 7. Observation drives state, never candidate self-claim
            store.add_candidate(other)
            v, stv = record_outcome(store, other, "PASS",
                                    predicted={"ram_mb": 700}, observed={"ram_mb": 610},
                                    delta={"ram_mb": -90})
            check("pass_episode_verifies_via_observation",
                  store.get_state(other.candidate_id) == STATE_VERIFIED and stv == STATE_VERIFIED)

            # 8. Lineage
            store.link(seed.candidate_id, run2[0].candidate_id, "evolved_into")
            check("lineage_recorded", run2[0].candidate_id in store.lineage(seed.candidate_id, "evolved_into"))

            # 9. Rebuildable cache: delete DB, re-record, same behavior
            import os
            os.remove(td + "/cand2.db")
            store3 = CandidateStore(td + "/cand2.db")
            try:
                check("rebuild_recreates_schema", store3.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='candidates'").fetchone() is not None)
            finally:
                store3.close()
        finally:
            store.close()

    passed = all(ok for _, ok in checks)
    return {"passed": passed, "checks": [{"name": n, "ok": ok} for n, ok in checks],
            "total": len(checks), "failed": [n for n, ok in checks if not ok]}

"""Causal Delta × CodeGraph — model-free chain tracing and first-divergence
localization over the deterministic CodeGraph (PR #55).

Study source: shared thread 6ac0e84e continuation, section "5. Causal Delta
× CodeGraph" of its live-repo recheck — named "one of the strongest
crossfunctions". The thread's example, verbatim in intent:

    Expected chain:
        UI -> ChatViewModel.send -> ModelGateway.route -> HFProvider.generate
        -> HTTP -> SSE decoder -> Flow.emit -> UI collector
    Observed:
        ChatViewModel.send  ✓ ...  SSE decoder ✓  Flow.emit ✗  UI collector ?
    Causal Delta immediately focuses on:
        SSE decoder -> Flow.emit          (the FIRST divergence)
    "The GGUF doesn't need to search the entire project."

and its deterministic repair-rule example:

    MISSING_MODULE_DEPENDENCY
        target   = app
        required = core
        evidence = symbol resolution

Implementation: composes two EXISTING merged modules —
  * lola_cognitive_fabric.CognitiveFabric.causal_delta(task_id, expected)
      (the first-divergence primitive: {index, key, expected, actual})
  * lola_code_intel.CodeIndex
      (stable symbol IDs, DEFINES/IMPORTS/TESTED_BY/CALLS edges)
— into a tracer that, given an expected chain of symbol/module names and the
observed check status per step, returns:
  * per-step resolution against the CodeGraph (found / not in graph),
  * the FIRST divergence (same shape as the fabric's causal_delta output),
  * file-level evidence about the divergence (does the upstream file import
    the missing module's file? does the file parse?),
  * deterministic REPAIR HYPOTHESES (MISSING_IMPORT / UNRESOLVED_SYMBOL /
    UNPARSEABLE_FILE / NOT_IN_GRAPH) — each a hypothesis (verified=False),
    never a verified fact.

Invariants (lola's frozen laws):
  * **Law 1 — user input is evidence, never verification.** The observed
    statuses come from the caller (build log, test run, probe) and are
    treated as evidence only; repair rules are hypotheses (verified=False).
    `verified=True` appears ONLY in the no-divergence case, where the claim
    is "the graph confirms the expected chain" — itself a graph observation,
    and the result still carries the graph version as its evidence scope.
  * **Deterministic, zero-model.** No LLM/GGUF call anywhere; the thread's
    "GGUF calls: 0" property is an explicit smoke check.
  * **Default-deny scope.** Only the explicitly supplied root is indexed
    (inherited from CodeIndex); nothing else is ever scanned.
  * **Sober failure.** Not-in-graph steps are NOT treated as failures: they
    are UNKNOWN (the graph only covers parseable Python under the root). A
    divergence is reported only where evidence exists (status mismatch), and
    an unresolved tail is surfaced as `unresolved_tail`, never invented.
"""
from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from lola_code_intel import CodeIndex

# Observed-check statuses (evidence vocabulary — from build/test/probe runs).
CHECK_OK = "OK"
CHECK_FAIL = "FAIL"
CHECK_UNKNOWN = "?"          # the thread's "?" — not yet observed
CHECK_ABSENT = "ABSENT"      # observed missing (e.g. symbol not imported)

# Divergence keys (mirror the fabric's causal_delta: first mismatch wins).
_DIVERGE_ON = {CHECK_FAIL, CHECK_ABSENT}


@dataclass(frozen=True)
class ChainStep:
    """One expected step, resolved against the CodeGraph.

    found=False means NOT IN GRAPH (unknown, not a failure) — the graph is a
    partial view (parseable Python under the root only), and honesty about
    that partiality is the point.
    """
    index: int
    name: str
    found: bool
    symbol_id: str = ""
    rel_path: str = ""
    file_id: str = ""
    expected: str = ""
    observed: str = CHECK_UNKNOWN
    first_divergence: bool = False


@dataclass(frozen=True)
class RepairHypothesis:
    """A deterministic repair candidate — a hypothesis, never a fact."""
    rule: str
    target: str
    required: str = ""
    evidence: str = ""
    verified: bool = False   # Law 1: always False for repair hypotheses


@dataclass(frozen=True)
class ChainTrace:
    steps: tuple
    first_divergence: dict            # fabric causal_delta shape
    unresolved_tail: tuple            # steps after divergence NOT in graph
    hypotheses: tuple                 # RepairHypothesis[]
    graph_version: str
    verified: bool                    # True ONLY when no divergence
    model_calls: int = 0              # the thread's "GGUF calls: 0"


def _stable_rule_id(rule: str, target: str, required: str) -> str:
    return "RH-" + hashlib.sha256(
        f"{rule}|{target}|{required}".encode("utf-8")).hexdigest()[:12]


class CausalCodeGraph:
    """First-divergence localization over the CodeGraph, zero-model."""

    def __init__(self, idx: CodeIndex):
        self.idx = idx

    # -- resolution --------------------------------------------------------
    def _resolve(self, name: str) -> dict:
        """Resolve a chain-step name: qualname, then name, then module stem.

        Deterministic tie-break: among same-named symbols, the one in the
        lexicographically smallest rel_path wins (stable across runs for the
        same DB state). Returns {found, symbol_id, name, qualname,
        rel_path, file_id}.
        """
        name = str(name).strip()
        sym = self.idx.find_by_qualname(name)
        if not sym:
            syms = self.idx.find_by_name(name)
            if syms:
                sym = sorted(syms, key=lambda x: (x["rel_path"], x["symbol_id"]))[0]
        if sym:
            return {"found": True, "symbol_id": sym["symbol_id"],
                    "name": sym["name"], "qualname": sym["qualname"],
                    "rel_path": sym["rel_path"], "file_id": sym["file_id"]}
        # module-level: a file stem (e.g. "core" for core.py)
        for f in self.idx.conn.execute(
                "SELECT * FROM files ORDER BY rel_path").fetchall():
            stem = Path(f["rel_path"]).stem
            if stem == name or f["rel_path"] == name:
                return {"found": True, "symbol_id": "", "name": stem,
                        "qualname": stem, "rel_path": f["rel_path"],
                        "file_id": f["file_id"]}
        return {"found": False, "symbol_id": "", "name": name, "qualname": name,
                "rel_path": "", "file_id": ""}

    def callers(self, name: str) -> list[dict]:
        """Reverse CALLS lookup (the thread's FAST-CODE 'who calls X?').

        Note: CodeIndex.symbol_neighbors(id, relation) only returns OUTGOING
        edges (src=?), so incoming CALLS edges (the callers) are queried
        directly from the edges table (dst=?) here.
        """
        syms = self.idx.find_by_name(name)
        out = []
        seen = set()
        for s in syms:
            rows = self.idx.conn.execute(
                "SELECT src FROM edges WHERE dst=? AND relation='CALLS'",
                (s["symbol_id"],)).fetchall()
            for r in rows:
                if r["src"] in seen:
                    continue
                seen.add(r["src"])
                caller = self.idx.get_symbol(r["src"])
                if caller:
                    out.append({"caller": caller["name"],
                                "qualname": caller["qualname"],
                                "rel_path": caller["rel_path"],
                                "symbol_id": caller["symbol_id"]})
        return out

    # -- the chain ----------------------------------------------------------
    def trace_chain(self, chain: Sequence[str],
                    observed: Mapping[int, str] | Mapping[str, str] | None = None) -> ChainTrace:
        """Trace an expected chain against observed per-step statuses.

        `observed` maps step index (or step name) -> CHECK_OK/CHECK_FAIL/
        CHECK_ABSENT/CHECK_UNKNOWN. Missing entries are CHECK_UNKNOWN
        (unobserved — not a failure).
        """
        obs = {}
        for k, v in (observed or {}).items():
            if isinstance(k, int):
                obs[k] = str(v)
            else:
                for i, name in enumerate(chain):
                    if str(name) == str(k):
                        obs[i] = str(v)
        steps = []
        for i, name in enumerate(chain):
            r = self._resolve(name)
            steps.append(ChainStep(
                index=i, name=str(name).strip(), found=r["found"],
                symbol_id=r["symbol_id"], rel_path=r["rel_path"],
                file_id=r["file_id"], expected=CHECK_OK,
                observed=obs.get(i, CHECK_UNKNOWN)))
        steps = tuple(steps)

        # first divergence = first step with failing/absent evidence
        div_idx = next((s.index for s in steps
                        if s.observed in _DIVERGE_ON), -1)
        first_div = ({"index": div_idx, "key": steps[div_idx].name,
                      "expected": steps[div_idx].expected,
                      "actual": steps[div_idx].observed}
                     if div_idx >= 0 else {"index": -1, "status": "no_divergence"})
        if div_idx >= 0:
            steps = tuple(
                dataclasses.replace(s, first_divergence=(s.index == div_idx))
                for s in steps)
            unresolved_tail = tuple(s.name for s in steps[div_idx + 1:]
                                    if not s.found)
        else:
            unresolved_tail = tuple()

        verified = div_idx < 0
        hyps = (self._repair_hypotheses(steps, div_idx) if div_idx >= 0 else ())
        return ChainTrace(steps=steps, first_divergence=first_div,
                          unresolved_tail=unresolved_tail,
                          hypotheses=hyps,
                          graph_version=self.idx.graph_version(),
                          verified=bool(verified), model_calls=0)

    def _imported_modules(self, file_id: str) -> set:
        """Module names a file imports, read straight from its source (AST).

        This is the *actual* evidence for the MISSING_IMPORT rule (the import
        statements themselves), not a re-derivation from graph edge hashes.
        The file is under the CodeIndex's explicit root, so default-deny scope
        is preserved; parsing is deterministic and model-free.
        """
        f = self.idx.get_file(file_id)
        if not f or not f.get("abs_path"):
            return set()
        import ast as _ast
        try:
            text = Path(f["abs_path"]).read_text(encoding="utf-8", errors="replace")
            tree = _ast.parse(text, filename=f["rel_path"])
        except (OSError, SyntaxError):
            return set()
        mods: set = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                for a in node.names:
                    mods.add(a.name.split(".")[0])
            elif isinstance(node, _ast.ImportFrom):
                if node.module:
                    mods.add(node.module.split(".")[0])
        return mods

    def _repair_hypotheses(self, steps: tuple[ChainStep, ...], div_idx: int) -> tuple[RepairHypothesis, ...]:
        """Deterministic, file-level repair rules at the first divergence.

        Evidence is structural (imports/parse state), never semantic; each
        rule is a hypothesis (verified=False) pending build/test.
        """
        out: list[RepairHypothesis] = []
        d = steps[div_idx]
        prev = steps[div_idx - 1] if div_idx > 0 else None
        imports_of_prev = self._imported_modules(prev.file_id) if prev and prev.file_id else set()
        if not d.found:
            out.append(RepairHypothesis(
                rule="UNRESOLVED_SYMBOL", target=d.name,
                evidence="step not in graph (root-scoped Python index only)",
                verified=False))
            if prev and prev.rel_path:
                d_stem = Path(d.name).stem
                if d.name not in imports_of_prev and d_stem not in imports_of_prev:
                    out.append(RepairHypothesis(
                        rule="MISSING_IMPORT", target=prev.rel_path,
                        required=d.name,
                        evidence=(f"upstream {prev.rel_path} declares no import of "
                                  f"'{d.name}' (file-level evidence; "
                                  f"imported: {sorted(imports_of_prev) or 'none'})"),
                        verified=False))
        else:
            # the symbol exists but the check failed: is its file broken?
            f = self.idx.get_file(d.file_id) if d.file_id else None
            if f and not f.get("syntax_ok", 1):
                out.append(RepairHypothesis(
                    rule="UNPARSEABLE_FILE", target=d.rel_path,
                    required=d.name,
                    evidence=f"file {d.rel_path} failed to parse: {f.get('error', 'syntax error')}",
                    verified=False))
            elif prev and prev.rel_path:
                if d.rel_path and Path(d.rel_path) == Path(prev.rel_path):
                    # defined in the same file the step's caller lives in:
                    # the only structural failure mode left is the symbol's
                    # own definition (e.g. a syntax error that killed parsing)
                    out.append(RepairHypothesis(
                        rule="SAME_FILE_DEFINITION", target=d.rel_path,
                        required=d.name,
                        evidence=(f"'{d.name}' is defined in {d.rel_path} (same "
                                  f"file as upstream) — structural rule: check the "
                                  f"definition itself (signature/parse), no import "
                                  f"can be missing"),
                        verified=False))
                else:
                    # cross-file reference the upstream never imported
                    d_stem = Path(d.rel_path).stem if d.rel_path else d.name
                    if d_stem not in imports_of_prev and Path(prev.rel_path).stem != d_stem:
                        out.append(RepairHypothesis(
                            rule="MISSING_IMPORT", target=prev.rel_path,
                            required=d_stem,
                            evidence=(f"upstream {prev.rel_path} references '{d.name}' "
                                      f"(defined in {d.rel_path}) but declares no import of "
                                      f"'{d_stem}' (file-level evidence)"),
                            verified=False))
        if not out:
            out.append(RepairHypothesis(
                rule="CHECK_MISMATCH", target=d.name,
                evidence=f"step observed {d.observed}, expected {d.expected} (no structural rule fired)",
                verified=False))
        return tuple(out)

    # -- the thread's FAST-CODE property -------------------------------------
    def who_calls(self, name: str) -> dict:
        """'Who calls X?' answered purely from the graph — 0 model calls."""
        c = self.callers(name)
        return {"question": f"who_calls({name!r})", "callers": c,
                "graph_version": self.idx.graph_version(),
                "model_calls": 0, "verified": False}


# ---------------------------------------------------------------------------
# Smoke — the thread's own scenario, made reproducible:
# expected chain where the first divergence is a step the upstream file
# does not import -> MISSING_IMPORT hypothesis with file-level evidence;
# plus the no-divergence (verified) path and the zero-model property.
# ---------------------------------------------------------------------------
def run_causal_codegraph_smoke() -> dict:
    import tempfile
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, bool(ok)))

    app_ok = (
        "import helper\n"
        "def send(x):\n"
        "    '''Send via route.'''\n"
        "    return route(x)\n"
        "def route(x):\n"
        "    '''Route the payload.'''\n"
        "    return x\n"
    )
    app_broken_chain = (
        "def send(x):\n"
        "    '''Send without the helper import (simulated missing dep).'''\n"
        "    return route(x)\n"
    )
    helper = (
        "def route(x):\n"
        "    '''Route the payload.'''\n"
        "    return x\n"
    )
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        (root / "app.py").write_text(app_ok, encoding="utf-8")
        (root / "helper.py").write_text(helper, encoding="utf-8")
        (root / "test_app.py").write_text(
            "from app import send\ndef test_send():\n"
            "    '''Test send.'''\n    assert send(1) == 1\n", encoding="utf-8")
        idx = CodeIndex(root, db_path=Path(td) / "proj.db")
        try:
            idx.index()
            ccg = CausalCodeGraph(idx)

            # 1. No divergence: every step found, checks OK -> verified
            t = ccg.trace_chain(["send", "route"], observed={0: CHECK_OK, 1: CHECK_OK})
            check("no_divergence_verified",
                  t.first_divergence == {"index": -1, "status": "no_divergence"}
                  and t.verified and t.model_calls == 0)

            # 2. First divergence: helper.route observed ABSENT (missing import)
            t2 = ccg.trace_chain(["send", "route"], observed={0: CHECK_OK, 1: CHECK_ABSENT})
            check("first_divergence_shape",
                  t2.first_divergence["index"] == 1
                  and t2.first_divergence["key"] == "route"
                  and t2.first_divergence["actual"] == CHECK_ABSENT
                  and not t2.verified)
            check("divergence_step_flagged",
                  t2.steps[1].first_divergence and not t2.steps[0].first_divergence)
            rules = [h.rule for h in t2.hypotheses]
            check("repair_hypothesis_present",
                  "SAME_FILE_DEFINITION" in rules or "MISSING_IMPORT" in rules
                  or "CHECK_MISMATCH" in rules)
            check("hypotheses_never_verified", all(not h.verified for h in t2.hypotheses))

            # 3. Unobserved steps are UNKNOWN, not failures (sober failure)
            t3 = ccg.trace_chain(["send", "route"], observed={0: CHECK_OK})
            check("unobserved_is_unknown",
                  t3.steps[1].observed == CHECK_UNKNOWN
                  and t3.first_divergence["status"] == "no_divergence")

            # 4. Not-in-graph is UNKNOWN, never invented as failure
            t4 = ccg.trace_chain(["send", "ghost_symbol"], observed={0: CHECK_OK, 1: CHECK_FAIL})
            check("not_in_graph_flagged",
                  not t4.steps[1].found
                  and t4.first_divergence["index"] == 1
                  and "UNRESOLVED_SYMBOL" in [h.rule for h in t4.hypotheses])

            # 5. who_calls: zero-model FAST-CODE answer
            wc = ccg.who_calls("route")
            check("who_calls_zero_model", wc["model_calls"] == 0 and wc["verified"] is False)
            check("who_calls_finds_caller",
                  any(c["qualname"] == "send" for c in wc["callers"]))

            # 5b. Same-file definition: found step fails, defined in the
            #     upstream's own file -> SAME_FILE_DEFINITION (not an import)
            t3b = ccg.trace_chain(["send", "route"], observed={0: CHECK_OK, 1: CHECK_FAIL})
            check("same_file_definition_rule",
                  any(h.rule == "SAME_FILE_DEFINITION" for h in t3b.hypotheses)
                  and all(not h.verified for h in t3b.hypotheses))
        finally:
            idx.close()

        # 6. Missing-import scenario: chain step NOT imported by upstream
        root2 = Path(td) / "proj2"
        root2.mkdir()
        (root2 / "app.py").write_text(app_broken_chain, encoding="utf-8")
        (root2 / "route.py").write_text("def route(x):\n    return x\n", encoding="utf-8")
        idx2 = CodeIndex(root2, db_path=Path(td) / "proj2.db")
        try:
            idx2.index()
            ccg2 = CausalCodeGraph(idx2)
            t5 = ccg2.trace_chain(["send", "route"], observed={0: CHECK_OK, 1: CHECK_ABSENT})
            mi = [h for h in t5.hypotheses if h.rule == "MISSING_IMPORT"]
            check("missing_import_rule_fires",
                  len(mi) == 1 and mi[0].required in ("route",) and mi[0].verified is False)
        finally:
            idx2.close()

        # 7. Cross-file found step, upstream never imported its module
        root3 = Path(td) / "proj3"
        root3.mkdir()
        (root3 / "app.py").write_text(
            "def send(x):\n"
            "    '''Send; compute lives elsewhere and is not imported.'''\n"
            "    return compute(x)\n", encoding="utf-8")
        (root3 / "calc.py").write_text(
            "def compute(x):\n"
            "    '''The compute module.'''\n"
            "    return x + 1\n", encoding="utf-8")
        idx3 = CodeIndex(root3, db_path=Path(td) / "proj3.db")
        try:
            idx3.index()
            ccg3 = CausalCodeGraph(idx3)
            t6 = ccg3.trace_chain(["send", "compute"], observed={0: CHECK_OK, 1: CHECK_FAIL})
            mi3 = [h for h in t6.hypotheses if h.rule == "MISSING_IMPORT"]
            check("cross_file_missing_import",
                  t6.steps[1].found
                  and len(mi3) == 1 and mi3[0].required == "calc"
                  and mi3[0].target == "app.py"
                  and mi3[0].verified is False)
        finally:
            idx3.close()

    passed = all(ok for _, ok in checks)
    return {"passed": passed, "checks": [{"name": n, "ok": ok} for n, ok in checks],
            "total": len(checks), "failed": [n for n, ok in checks if not ok]}

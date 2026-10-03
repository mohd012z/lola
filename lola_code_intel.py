"""Code Intelligence layer — deterministic identifiers, incremental code index,
SQLite CodeGraph, FTS5 hybrid retrieval, and a compact context compiler.

Study source: the shared GGUF deep-dive thread (6ac0d1f0), whose final two
sections re-inspected the actual lola repository and concluded "merge, not
replace" — lola's kernel/cognition/governance is already strong; the missing
layer is a *fast deterministic code-intelligence foundation* that "makes the
GGUF do less work". This module implements that foundation (the thread's P0 +
P1 + P2):

    exact lookup  ->  graph lookup  ->  lexical (FTS5)  ->  (vector: later)

Design invariants (aligned with lola's frozen laws):
  * **Deterministic, zero-model.** No LLM / GGUF call anywhere. Indexing,
    retrieval and context compilation are pure stdlib (ast + sqlite3 + hashlib).
  * **Default-deny scope.** Only files under an explicitly supplied root are
    indexed; nothing else on disk is ever scanned.
  * **Evidence, not verification.** The graph is *derived evidence* about
    structure; it never claims code is correct. Compiled context carries
    ``verified=False`` by default (Law 1).
  * **Fail-closed, not silent.** A file that fails to parse is recorded with a
    reason and excluded from the graph — never dropped silently.
  * **Incremental.** Re-indexing re-parses only files whose content hash
    changed (DeltaIndexer), so cost is proportional to the change, not the repo.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

# Directories never scanned (mirrors the repo's compile/test skip rules).
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", "build", "dist",
    ".lola-tools", ".venv", "venv", ".pytest_cache", ".mypy_cache",
}

# Stable edge-relation vocabulary for the graph.
REL_DEFINES = "DEFINES"      # file -> class / function
REL_CALLS = "CALLS"          # function -> function (resolved by local name)
REL_IMPORTS = "IMPORTS"      # file -> module name
REL_TESTED_BY = "TESTED_BY"  # symbol -> test function that calls it

_FTS_LIMIT = 4000  # per-cell FTS text cap keeps snippets bounded


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _stable_id(prefix: str, *parts: str) -> str:
    """A stable, compact, identity-derived ID: TYPE:<12 hex>.

    Deterministic across machines/runs: a symbol keeps its ID as long as its
    identity (file + qualified name) is unchanged.
    """
    return prefix + ":" + _sha("|".join(parts))[:12]


@dataclass
class FileRecord:
    rel_path: str
    file_id: str
    content_hash: str
    num_lines: int
    syntax_ok: bool
    error: str = ""


@dataclass
class Symbol:
    symbol_id: str
    kind: str            # "function" | "method" | "class"
    name: str
    qualname: str
    file_id: str
    rel_path: str
    start_line: int
    end_line: int
    docstring: str = ""


@dataclass
class Edge:
    src: str
    dst: str
    relation: str


@dataclass
class IndexStats:
    root: str
    graph_version: str
    files_total: int
    files_reindexed: int
    files_unchanged: int
    files_removed: int
    files_failed: int
    files_failed_list: list
    symbols: int
    edges: int
    fts_available: bool
    elapsed_ms: float


@dataclass
class RetrievalHit:
    stage: str           # "exact" | "graph" | "lexical"
    node_id: str
    node_type: str       # "symbol" | "file" | "module"
    name: str
    rel_path: str
    start_line: int
    score: float
    detail: str = ""


@dataclass
class CompiledContext:
    target_id: str
    target: dict
    callers: list
    callees: list
    tests: list
    graph_version: str
    source: str = "code_intel"
    verified: bool = False  # evidence, not verification (Law 1)
    model_calls: int = 0    # this layer never calls a model
    stale: bool = False     # True only when check_staleness=True AND the
                            # index's file hashes no longer match disk


@dataclass
class StalenessReport:
    """Read-only answer to: 'does this index still match the source tree?'

    Thread weakness #10 ('index staleness'): 'Never trust an index whose
    source hash doesn't match.'  This probe hashes every file under the
    root (no parsing, no writes) and compares against the recorded file
    hashes — so a consumer can decide to reindex BEFORE reasoning from a
    possibly-stale graph.  Cost is O(files) hash work; it performs NO
    reindexing itself (that remains an explicit, separate act).
    """
    is_fresh: bool
    changed: tuple[str, ...]      # indexed, on disk, hash differs
    removed: tuple[str, ...]      # indexed, no longer on disk
    unindexed: tuple[str, ...]    # on disk, not yet in the index
    unreadable: tuple[str, ...]   # on disk (indexed or not), could not be hashed

    def summary(self) -> str:
        if self.is_fresh:
            return "fresh"
        parts = []
        if self.changed:
            parts.append(f"changed={len(self.changed)}")
        if self.removed:
            parts.append(f"removed={len(self.removed)}")
        if self.unindexed:
            parts.append(f"unindexed={len(self.unindexed)}")
        if self.unreadable:
            parts.append(f"unreadable={len(self.unreadable)}")
        return "stale (" + ", ".join(parts) + ")"


class CodeIndex:
    """A persistent, incremental SQLite-backed code index for a root directory.

    The DB file lives OUTSIDE the scanned root (default: a sibling
    ``<root>.codeintel.sqlite``) so indexing a project never mutates it.
    """

    def __init__(self, root: str | Path, db_path: str | Path | None = None):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"code-intel root is not a directory: {self.root}")
        if db_path is None:
            db_path = self.root.parent / (self.root.name + ".codeintel.sqlite")
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        # The index DB is a pure, rebuildable cache (no user data) — so
        # memory journaling + no sync is a safe speed win (600x faster DDL in
        # fsync-heavy environments).
        self.conn.execute("PRAGMA journal_mode=MEMORY")
        self.conn.execute("PRAGMA synchronous=OFF")
        self._init_schema()

    # -- schema -----------------------------------------------------------
    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
                file_id   TEXT PRIMARY KEY,
                rel_path  TEXT UNIQUE NOT NULL,
                abs_path  TEXT NOT NULL,
                hash      TEXT NOT NULL,
                num_lines INTEGER NOT NULL,
                syntax_ok INTEGER NOT NULL,
                error     TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS symbols (
                symbol_id  TEXT PRIMARY KEY,
                kind       TEXT NOT NULL,
                name       TEXT NOT NULL,
                qualname   TEXT NOT NULL,
                file_id    TEXT NOT NULL,
                rel_path   TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line   INTEGER NOT NULL,
                docstring  TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS edges (
                src      TEXT NOT NULL,
                dst      TEXT NOT NULL,
                relation TEXT NOT NULL,
                PRIMARY KEY (src, dst, relation)
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE INDEX IF NOT EXISTS idx_sym_name ON symbols(name);
            CREATE INDEX IF NOT EXISTS idx_sym_qual ON symbols(qualname);
            CREATE INDEX IF NOT EXISTS idx_sym_file ON symbols(file_id);
            CREATE INDEX IF NOT EXISTS idx_edge_dst ON edges(dst);
            CREATE INDEX IF NOT EXISTS idx_edge_src ON edges(src);
            """
        )
        # FTS5 is present in the runtime python; if a build lacks it, degrade
        # retrieval to exact/graph only (still deterministic), never crash.
        # Tables are created lazily (on the first index that has symbols) so
        # repeated connections don't pay FTS creation cost for unchanged trees.
        self._fts_ok = None
        self._fts_ready = False
        self.conn.commit()

    def _ensure_fts(self) -> None:
        if self._fts_ready or self._fts_ok is False:
            return
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS fts_symbol USING fts5("
                "name, qualname, docstring, rel_path, content='')"
            )
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS fts_file USING fts5("
                "rel_path, snippet, content='')"
            )
            self._fts_ok = True
            self._fts_ready = True
        except sqlite3.OperationalError:
            self._fts_ok = False

    # -- discovery --------------------------------------------------------
    def _iter_py_files(self) -> Iterable[Path]:
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in sorted(dirnames) if d not in _SKIP_DIRS]
            for fn in sorted(filenames):
                if fn.endswith(".py"):
                    yield Path(dirpath) / fn

    # -- indexing ---------------------------------------------------------
    def index(self) -> IndexStats:
        t0 = time.monotonic()
        prev = {r["rel_path"]: r["hash"]
                for r in self.conn.execute("SELECT rel_path, hash FROM files")}

        reindexed = 0
        unchanged = 0
        seen: set[str] = set()
        self._ensure_fts()  # determines self._fts_ok for this run
        for path in self._iter_py_files():
            rel = path.relative_to(self.root).as_posix()
            seen.add(rel)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                self._store_failed_file(rel, str(path), "", 0, f"unreadable: {e}")
                reindexed += 1
                continue
            h = _sha(text)
            if prev.get(rel) == h:
                unchanged += 1
                continue
            rec, syms, edges = self._parse_file(path, rel, text)
            if rec is None:
                reindexed += 1
                continue
            self._store_file_and_symbols(rec, str(path), syms, edges)
            reindexed += 1

        # Remove files that disappeared from disk (and their symbols/edges).
        removed = 0
        for rel in list(prev):
            if rel not in seen:
                fid = _stable_id("F", rel)
                self._delete_file(fid)
                removed += 1

        # Refresh FTS only when the symbol set can have changed.
        if reindexed or removed:
            self._ensure_fts()
            self._refresh_fts()
        gv = self._graph_version()
        self.conn.execute("INSERT OR REPLACE INTO meta VALUES ('graph_version', ?)", (gv,))
        self.conn.commit()

        failed_rows = list(self.conn.execute(
            "SELECT rel_path, error FROM files WHERE syntax_ok = 0 ORDER BY rel_path"))
        return IndexStats(
            root=str(self.root), graph_version=gv,
            files_total=len(seen),
            files_reindexed=reindexed, files_unchanged=unchanged,
            files_removed=removed,
            files_failed=len(failed_rows),
            files_failed_list=[{"rel_path": r["rel_path"], "error": r["error"]}
                               for r in failed_rows],
            symbols=self.conn.execute("SELECT COUNT(*) c FROM symbols").fetchone()["c"],
            edges=self.conn.execute("SELECT COUNT(*) c FROM edges").fetchone()["c"],
            fts_available=self._fts_ok,
            elapsed_ms=round((time.monotonic() - t0) * 1000.0, 1),
        )

    # -- parse one file ----------------------------------------------------
    def _parse_file(self, path: Path, rel: str, text: str):
        lines = len(text.splitlines())
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError as e:
            self._store_failed_file(rel, str(path), _sha(text), lines,
                                    f"syntax: {e.msg} (line {e.lineno})")
            return None, None, None
        file_id = _stable_id("F", rel)
        syms: list[Symbol] = []
        edges: list[Edge] = []
        defined: dict[str, Symbol] = {}

        for fn in self._iter_defs(tree):
            sym = self._make_symbol(file_id, rel, fn)
            syms.append(sym)
            defined.setdefault(sym.name, sym)
            edges.append(Edge(file_id, sym.symbol_id, REL_DEFINES))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    edges.append(Edge(file_id, _stable_id("M", a.name), REL_IMPORTS))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    edges.append(Edge(file_id, _stable_id("M", node.module), REL_IMPORTS))

        for fn in self._iter_defs(tree):
            caller = self._make_symbol(file_id, rel, fn).symbol_id
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    callee = self._call_name(node.func)
                    tgt = defined.get(callee) if callee else None
                    if tgt and tgt.symbol_id != caller:
                        edges.append(Edge(caller, tgt.symbol_id, REL_CALLS))

        for sym in syms:
            if sym.kind == "function" and sym.name.startswith("test_"):
                for fn in self._iter_defs(tree):
                    if self._make_symbol(file_id, rel, fn).symbol_id == sym.symbol_id:
                        for node in ast.walk(fn):
                            if isinstance(node, ast.Call):
                                callee = self._call_name(node.func)
                                tgt = defined.get(callee) if callee else None
                                if tgt and tgt.symbol_id != sym.symbol_id:
                                    edges.append(Edge(tgt.symbol_id, sym.symbol_id,
                                                     REL_TESTED_BY))

        rec = FileRecord(rel, file_id, _sha(text), lines, True, "")
        return rec, syms, edges

    def _iter_defs(self, tree):
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node._qualname = node.name  # type: ignore[attr-defined]
                yield node
            elif isinstance(node, ast.ClassDef):
                node._qualname = node.name  # type: ignore[attr-defined]
                yield node
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        sub._qualname = f"{node.name}.{sub.name}"  # type: ignore[attr-defined]
                        yield sub

    def _make_symbol(self, file_id, rel, node) -> Symbol:
        if isinstance(node, ast.ClassDef):
            kind = "class"
        elif self._is_method(node):
            kind = "method"
        else:
            kind = "function"
        qual = getattr(node, "_qualname", node.name)
        doc = ast.get_docstring(node) or ""
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        return Symbol(
            symbol_id=_stable_id("S", file_id, qual),
            kind=kind, name=node.name, qualname=qual,
            file_id=file_id, rel_path=rel,
            start_line=node.lineno, end_line=end, docstring=doc[:_FTS_LIMIT])

    @staticmethod
    def _is_method(node) -> bool:
        args = getattr(node, "args", None)
        if args and args.args:
            return args.args[0].arg in ("self", "cls")
        return False

    @staticmethod
    def _call_name(func) -> str | None:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None

    # -- persistence -------------------------------------------------------
    def _store_file_and_symbols(self, rec: FileRecord, abs_path: str,
                                syms: list[Symbol], edges: list[Edge]) -> None:
        self.conn.execute("DELETE FROM symbols WHERE file_id=?", (rec.file_id,))
        self.conn.execute("DELETE FROM edges WHERE src=? OR dst=?",
                          (rec.file_id, rec.file_id))
        self.conn.execute(
            "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?)",
            (rec.file_id, rec.rel_path, abs_path, rec.content_hash,
             rec.num_lines, 1, rec.error))
        for s in syms:
            self.conn.execute(
                "INSERT OR REPLACE INTO symbols VALUES (?,?,?,?,?,?,?,?,?)",
                (s.symbol_id, s.kind, s.name, s.qualname, s.file_id,
                 s.rel_path, s.start_line, s.end_line, s.docstring))
        for e in edges:
            self.conn.execute("INSERT OR IGNORE INTO edges VALUES (?,?,?)",
                              (e.src, e.dst, e.relation))

    def _store_failed_file(self, rel, abs_path, h, lines, error) -> None:
        self._delete_file(_stable_id("F", rel))
        self.conn.execute(
            "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?)",
            (_stable_id("F", rel), rel, abs_path, h, lines, 0, error))

    def _delete_file(self, file_id: str) -> None:
        self.conn.execute("DELETE FROM symbols WHERE file_id=?", (file_id,))
        self.conn.execute("DELETE FROM edges WHERE src=? OR dst=?",
                          (file_id, file_id))
        self.conn.execute("DELETE FROM files WHERE file_id=?", (file_id,))

    def _refresh_fts(self) -> None:
        if not self._fts_ok:
            return
        self.conn.execute("INSERT INTO fts_symbol(fts_symbol) VALUES('delete-all')")
        self.conn.execute("INSERT INTO fts_file(fts_file) VALUES('delete-all')")
        for s in self.conn.execute(
                "SELECT symbol_id,name,qualname,docstring,rel_path FROM symbols"):
            self.conn.execute(
                "INSERT INTO fts_symbol(rowid,name,qualname,docstring,rel_path) "
                "VALUES (?,?,?,?,?)",
                (self.conn.execute(
                    "SELECT rowid FROM symbols WHERE symbol_id=?",
                    (s["symbol_id"],)).fetchone()[0],
                 s["name"][:_FTS_LIMIT], s["qualname"][:_FTS_LIMIT],
                 s["docstring"], s["rel_path"][:_FTS_LIMIT]))
        for f in self.conn.execute("SELECT file_id, rel_path FROM files WHERE syntax_ok=1"):
            self.conn.execute(
                "INSERT INTO fts_file(rowid,rel_path,snippet) VALUES (?,?,?)",
                (self.conn.execute(
                    "SELECT rowid FROM files WHERE file_id=?",
                    (f["file_id"],)).fetchone()[0],
                 f["rel_path"][:_FTS_LIMIT], f["rel_path"][:_FTS_LIMIT]))

    def _graph_version(self) -> str:
        seed = self.conn.execute(
            "SELECT COALESCE(GROUP_CONCAT(file_id||':'||hash,';'),'') FROM files"
        ).fetchone()[0]
        return _stable_id("G", seed)

    # -- queries -----------------------------------------------------------
    def graph_version(self) -> str:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key='graph_version'").fetchone()
        return row["value"] if row else ""

    # -- staleness (read-only probe; thread weakness #10) ------------------
    def staleness_report(self) -> "StalenessReport":
        """Hash every file under the root (no parsing, NO writes) and compare
        with the recorded file hashes.  Returns a StalenessReport; performs
        no reindexing.  An unreadable indexed file counts as unreadable, not
        silently fresh (fail-closed)."""
        prev = {r["rel_path"]: r["hash"]
                for r in self.conn.execute("SELECT rel_path, hash FROM files")}
        changed: list[str] = []
        unindexed: list[str] = []
        unreadable: list[str] = []
        seen: set[str] = set()
        for path in self._iter_py_files():
            rel = path.relative_to(self.root).as_posix()
            seen.add(rel)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                unreadable.append(rel)
                continue
            h = _sha(text)
            if rel not in prev:
                unindexed.append(rel)
            elif prev[rel] != h:
                changed.append(rel)
        removed = [rel for rel in prev if rel not in seen]
        report = StalenessReport(
            is_fresh=not (changed or removed or unindexed or unreadable),
            changed=tuple(sorted(changed)),
            removed=tuple(sorted(removed)),
            unindexed=tuple(sorted(unindexed)),
            unreadable=tuple(sorted(unreadable)))
        return report

    def get_symbol(self, symbol_id: str) -> dict | None:
        r = self.conn.execute(
            "SELECT * FROM symbols WHERE symbol_id=?", (symbol_id,)).fetchone()
        return dict(r) if r else None

    def get_file(self, file_id: str) -> dict | None:
        r = self.conn.execute(
            "SELECT * FROM files WHERE file_id=?", (file_id,)).fetchone()
        return dict(r) if r else None

    def symbol_neighbors(self, symbol_id: str, relation: str | None = None) -> list:
        if relation:
            rows = self.conn.execute(
                "SELECT src, dst, relation FROM edges WHERE src=? AND relation=?",
                (symbol_id, relation)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT src, dst, relation FROM edges WHERE src=? OR dst=?",
                (symbol_id, symbol_id)).fetchall()
        return [dict(r) for r in rows]

    def find_by_name(self, name: str) -> list:
        rows = self.conn.execute(
            "SELECT * FROM symbols WHERE name=? ORDER BY qualname", (name,)).fetchall()
        return [dict(r) for r in rows]

    def find_by_qualname(self, qualname: str) -> dict | None:
        r = self.conn.execute(
            "SELECT * FROM symbols WHERE qualname=?", (qualname,)).fetchone()
        return dict(r) if r else None

    def close(self) -> None:
        self.conn.close()


def _hit_from_symbol(stage: str, s: dict, score: float, detail: str = "") -> RetrievalHit:
    return RetrievalHit(
        stage=stage, node_id=s["symbol_id"], node_type="symbol", name=s["name"],
        rel_path=s["rel_path"], start_line=s["start_line"], score=score, detail=detail)


def _hit_from_file(stage: str, f: dict, score: float, detail: str = "") -> RetrievalHit:
    return RetrievalHit(
        stage=stage, node_id=f["file_id"], node_type="file", name=f["rel_path"],
        rel_path=f["rel_path"], start_line=0, score=score, detail=detail)


class Retriever:
    """Hybrid retrieval: exact -> graph -> lexical (FTS5).

    Deterministic ordering (name, then qualname / path) so results are
    reproducible and testable. Lexical stage is skipped when FTS5 is absent.
    """

    def __init__(self, idx: CodeIndex):
        self.idx = idx

    def search(self, query: str, limit: int = 10) -> list[RetrievalHit]:
        q = query.strip()
        if not q:
            return []
        hits: list[RetrievalHit] = []
        seen: set[str] = set()

        # 1) exact: symbol name or qualified name
        for s in self.idx.find_by_name(q):
            h = _hit_from_symbol("exact", s, 1.0)
            seen.add(h.node_id); hits.append(h)
        s = self.idx.find_by_qualname(q)
        if s and s["symbol_id"] not in seen:
            h = _hit_from_symbol("exact", s, 1.0)
            seen.add(h.node_id); hits.append(h)

        # 2) graph: if the query named a symbol, surface its direct neighbors
        anchor = self.idx.find_by_qualname(q) or (
            self.idx.find_by_name(q) or [None])[0]
        if anchor:
            for e in self.idx.symbol_neighbors(anchor["symbol_id"]):
                other = e["dst"] if e["src"] == anchor["symbol_id"] else e["src"]
                s = self.idx.get_symbol(other)
                if s and s["symbol_id"] not in seen:
                    h = _hit_from_symbol("graph", s, 0.6, detail=f"{e['relation']} of {q}")
                    seen.add(h.node_id); hits.append(h)

        # 3) lexical: FTS5 over symbols, ranked. Try AND (all terms) first;
        #        fall back to OR (any term) so multi-word prose still matches.
        if self.idx._fts_ok:
            tokens = q.split()
            variants = []
            if len(tokens) > 1:
                variants.append(" ".join('"%s"' % t for t in tokens))  # AND
                variants.append(" OR ".join('"%s"' % t for t in tokens))  # OR
            variants.append('"%s"' % q)
            for fts_q in variants:
                try:
                    rows = self.idx.conn.execute(
                        "SELECT s.* FROM fts_symbol f JOIN symbols s "
                        "ON s.rowid = f.rowid WHERE fts_symbol MATCH ? "
                        "ORDER BY bm25(fts_symbol) LIMIT ?", (fts_q, limit)).fetchall()
                except sqlite3.OperationalError:
                    continue  # malformed FTS query -> try next variant
                if rows:
                    for r in rows:
                        if r["symbol_id"] not in seen:
                            h = _hit_from_symbol("lexical", dict(r), 0.3)
                            seen.add(h.node_id); hits.append(h)
                    break

        return hits[:limit]


class ContextCompiler:
    """Builds a tiny, evidence-only context for a target symbol.

    Produces target + callers + callees + tests + file, all as stable IDs and
    coordinates. ``verified`` is always False (Law 1): this is structural
    evidence for a model to use, not a correctness claim.
    """

    def __init__(self, idx: CodeIndex):
        self.idx = idx

    def compile(self, target_id: str, include_source: bool = False,
                check_staleness: bool = False) -> CompiledContext:
        stale = False
        if check_staleness:
            # Read-only probe; the context carries the verdict so a caller
            # never silently reasons from a stale graph (weakness #10).
            stale = not self.idx.staleness_report().is_fresh
        s = self.idx.get_symbol(target_id)
        if not s:
            return CompiledContext(
                target_id=target_id, target={}, callers=[], callees=[],
                tests=[], graph_version=self.idx.graph_version(), stale=stale)
        callers, callees, tests = [], [], []
        for e in self.idx.symbol_neighbors(target_id):
            if e["relation"] == REL_CALLS:
                if e["dst"] == target_id:      # someone calls target -> caller
                    other = e["src"]
                    osym = self.idx.get_symbol(other)
                    if osym:
                        callers.append(self._brief(osym))
                else:                            # target calls other -> callee
                    other = e["dst"]
                    osym = self.idx.get_symbol(other)
                    if osym:
                        callees.append(self._brief(osym))
            elif e["relation"] == REL_TESTED_BY and e["dst"] == target_id:
                osym = self.idx.get_symbol(e["src"])
                if osym:
                    tests.append(self._brief(osym))
        f = self.idx.get_file(s["file_id"]) or {}
        target = self._brief(s)
        target["file"] = f.get("rel_path", s["rel_path"])
        target["num_lines"] = f.get("num_lines")
        if include_source:
            target["source_lines"] = [s["start_line"], s["end_line"]]
        return CompiledContext(
            target_id=target_id, target=target,
            callers=self._dedupe(callers), callees=self._dedupe(callees),
            tests=self._dedupe(tests), graph_version=self.idx.graph_version(),
            stale=stale)

    @staticmethod
    def _brief(s: dict) -> dict:
        return {
            "id": s["symbol_id"], "kind": s["kind"], "name": s["name"],
            "qualname": s["qualname"], "file": s["rel_path"],
            "line": s["start_line"],
        }

    @staticmethod
    def _dedupe(items: list) -> list:
        seen = set(); out = []
        for it in items:
            if it["id"] not in seen:
                seen.add(it["id"]); out.append(it)
        return out


def run_code_intel_smoke() -> dict:
    """Deterministic self-test on a synthetic in-memory tree (temp files).

    Proves the whole layer end-to-end with zero external models:
      * index builds a graph with stable IDs
      * exact / graph / lexical retrieval all hit
      * incremental reindex touches only changed files
      * context compiler assembles target+callers+callees+tests
      * fail-closed: a syntax-broken file is recorded, not silent
    """
    import tempfile
    results: dict = {"checks": [], "passed": True}

    def check(name: str, ok: bool, detail: str = ""):
        results["checks"].append({"name": name, "passed": bool(ok), "detail": detail})
        if not ok:
            results["passed"] = False

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        (root / "app.py").write_text(
            "import helper\n"
            "def helper_add(a, b):\n"
            "    '''Add two numbers.'''\n"
            "    return a + b\n"
            "def compute(x):\n"
            "    '''Compute via helper.'''\n"
            "    return helper_add(x, 1)\n"
            "def run():\n"
            "    return compute(5)\n", encoding="utf-8")
        (root / "test_app.py").write_text(
            "from app import compute\n"
            "def test_compute():\n"
            "    '''Test compute.'''\n"
            "    assert compute(5) == 6\n"
            "    run_compute()\n"
            "def run_compute():\n"
            "    return compute(1)\n", encoding="utf-8")
        (root / "broken.py").write_text("def oops(:\n", encoding="utf-8")

        db = Path(td) / "proj.codeintel.sqlite"
        idx = CodeIndex(root, db_path=db)
        st1 = idx.index()
        check("index builds graph", st1.symbols >= 4 and st1.edges >= 3,
              f"symbols={st1.symbols} edges={st1.edges}")
        check("fail-closed records broken file", st1.files_failed == 1
              and st1.files_failed_list[0]["rel_path"] == "broken.py",
              str(st1.files_failed_list))

        gv1 = idx.graph_version()
        check("graph version stable+nonempty", bool(gv1), gv1)

        # exact retrieval
        r = idx.find_by_qualname("compute")
        check("exact qualname lookup", bool(r) and r["name"] == "compute")

        # retrieval stages
        ret = Retriever(idx)
        h_exact = ret.search("compute")
        check("retrieval exact stage", any(h.stage == "exact" and h.name == "compute"
                                           for h in h_exact))
        h_graph = ret.search("compute")
        check("retrieval graph stage (neighbors)", any(h.stage == "graph"
                                                       for h in h_graph),
              f"stages={[h.stage for h in h_graph]}")
        h_lex = ret.search("Add two numbers")
        check("retrieval lexical stage (FTS5)", any(h.stage == "lexical"
                                                    for h in h_lex),
              f"fts={idx._fts_ok} hits={[h.name for h in h_lex]}")

        # context compiler
        cc = ContextCompiler(idx)
        compute_id = idx.find_by_qualname("compute")["symbol_id"]
        ctx = cc.compile(compute_id)
        check("context target set", ctx.target.get("name") == "compute")
        check("context callers (run->compute)", any(c["name"] == "run"
                                                    for c in ctx.callers),
              str(ctx.callers))
        check("context callees (compute->helper_add)", any(c["name"] == "helper_add"
                                                           for c in ctx.callees),
              str(ctx.callees))
        check("context verified=False (Law 1)", ctx.verified is False)
        check("context zero model calls", ctx.model_calls == 0)

        # incremental: change one file, reindex
        (root / "app.py").write_text(
            (root / "app.py").read_text() + "\ndef added():\n"
            "    '''Brand new.'''\n"
            "    return 1\n", encoding="utf-8")
        st2 = idx.index()
        check("incremental reindex only changed file",
              st2.files_reindexed == 1 and st2.files_unchanged >= 1,
              f"reindexed={st2.files_reindexed} unchanged={st2.files_unchanged}")
        check("graph version changes on content change",
              idx.graph_version() != gv1)

        # staleness (read-only probe; thread weakness #10)
        check("fresh after reindex", idx.staleness_report().is_fresh,
              idx.staleness_report().summary())
        (root / "app.py").write_text(
            (root / "app.py").read_text() + "\n# tail change\n", encoding="utf-8")
        (root / "new_file.py").write_text("def n():\n    return 2\n", encoding="utf-8")
        report = idx.staleness_report()
        check("detects changed file", "app.py" in report.changed, report.summary())
        check("detects unindexed file", "new_file.py" in report.unindexed,
              report.summary())
        check("stale not fresh", not report.is_fresh)
        # the probe must NOT have reindexed: graph version unchanged
        gv_before = idx.graph_version()
        idx.staleness_report()
        check("probe is read-only (no reindex)", idx.graph_version() == gv_before)
        # reindex clears staleness
        idx.index()
        check("reindex clears staleness", idx.staleness_report().is_fresh)
        # context compiler carries the verdict when asked
        ctx_stale = ContextCompiler(idx).compile(compute_id, check_staleness=True)
        check("context fresh when clean", ctx_stale.stale is False)
        (root / "app.py").write_text(
            (root / "app.py").read_text() + "# mutate\n", encoding="utf-8")
        ctx_dirty = ContextCompiler(idx).compile(compute_id, check_staleness=True)
        check("context flags stale graph", ctx_dirty.stale is True)
        check("context stale still verified=False (Law 1)",
              ctx_dirty.verified is False)

        idx.close()

    results["passed"] = bool(results["passed"])
    return results

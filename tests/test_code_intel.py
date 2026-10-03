"""Tests for the Code Intelligence layer (lola_code_intel).

Deterministic, zero-model: stable identifiers, incremental SQLite CodeGraph,
FTS5 hybrid retrieval, and the context compiler. Covers the layer's invariants
(deterministic IDs, fail-closed on bad syntax, incremental reindex, Law 1
evidence-not-verification) and the hybrid retrieval stages (exact -> graph ->
lexical).
"""
import tempfile
import unittest
from pathlib import Path

from lola_code_intel import (
    CodeIndex,
    ContextCompiler,
    Retriever,
    run_code_intel_smoke,
)

APP = (
    "import helper\n"
    "def helper_add(a, b):\n"
    "    '''Add two numbers.'''\n"
    "    return a + b\n"
    "def compute(x):\n"
    "    '''Compute via helper.'''\n"
    "    return helper_add(x, 1)\n"
    "def run():\n"
    "    return compute(5)\n"
)
TEST_APP = (
    "from app import compute\n"
    "def test_compute():\n"
    "    '''Test compute.'''\n"
    "    assert compute(5) == 6\n"
)


class CodeIntelIndexTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        root = Path(self._td.name) / "proj"
        root.mkdir()
        (root / "app.py").write_text(APP, encoding="utf-8")
        (root / "test_app.py").write_text(TEST_APP, encoding="utf-8")
        self.root = root
        self.idx = CodeIndex(root, db_path=Path(self._td.name) / "proj.db")
        self.stats = self.idx.index()

    def tearDown(self):
        self.idx.close()
        self._td.cleanup()

    def test_builds_symbols_and_edges(self):
        self.assertGreaterEqual(self.stats.symbols, 4)
        self.assertGreaterEqual(self.stats.edges, 3)
        self.assertEqual(self.stats.files_total, 2)

    def test_stable_ids_are_deterministic(self):
        a = self.idx.find_by_qualname("compute")
        b = self.idx.find_by_qualname("compute")
        self.assertIsNotNone(a)
        self.assertEqual(a["symbol_id"], b["symbol_id"])
        self.assertTrue(a["symbol_id"].startswith("S:"))

    def test_graph_version_stable_then_changes_on_content(self):
        gv1 = self.idx.graph_version()
        self.assertTrue(gv1)
        (self.root / "app.py").write_text(APP + "\ndef newf():\n    return 1\n",
                                          encoding="utf-8")
        st = self.idx.index()
        self.assertEqual(st.files_reindexed, 1)
        self.assertEqual(st.files_unchanged, 1)
        self.assertNotEqual(self.idx.graph_version(), gv1)

    def test_incremental_reindex_only_changed_files(self):
        # no content change -> reindex touches nothing
        st = self.idx.index()
        self.assertEqual(st.files_reindexed, 0)
        self.assertGreaterEqual(st.files_unchanged, 2)

    def test_fail_closed_records_broken_file(self):
        (self.root / "broken.py").write_text("def oops(:\n", encoding="utf-8")
        st = self.idx.index()
        self.assertEqual(st.files_failed, 1)
        self.assertEqual(st.files_failed_list[0]["rel_path"], "broken.py")
        self.assertIn("syntax", st.files_failed_list[0]["error"])


class CodeIntelStalenessTests(unittest.TestCase):
    """Thread weakness #10: 'Never trust an index whose source hash doesn't
    match.'  The staleness probe must be READ-ONLY (no reindex) so a consumer
    can decide whether to reindex BEFORE reasoning from the graph."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        root = Path(self._td.name) / "proj"
        root.mkdir()
        (root / "app.py").write_text(APP, encoding="utf-8")
        (root / "test_app.py").write_text(TEST_APP, encoding="utf-8")
        self.root = root
        self.idx = CodeIndex(root, db_path=Path(self._td.name) / "proj.db")
        self.idx.index()

    def tearDown(self):
        self.idx.close()
        self._td.cleanup()

    def test_fresh_after_index(self):
        r = self.idx.staleness_report()
        self.assertTrue(r.is_fresh, r.summary())

    def test_detects_changed_file(self):
        (self.root / "app.py").write_text(APP + "\n# mutated\n", encoding="utf-8")
        r = self.idx.staleness_report()
        self.assertFalse(r.is_fresh)
        self.assertIn("app.py", r.changed)

    def test_detects_removed_file(self):
        (self.root / "test_app.py").unlink()
        r = self.idx.staleness_report()
        self.assertFalse(r.is_fresh)
        self.assertIn("test_app.py", r.removed)

    def test_detects_unindexed_file(self):
        (self.root / "brand_new.py").write_text("def z():\n    return 0\n",
                                                encoding="utf-8")
        r = self.idx.staleness_report()
        self.assertFalse(r.is_fresh)
        self.assertIn("brand_new.py", r.unindexed)

    def test_probe_is_read_only(self):
        (self.root / "app.py").write_text(APP + "\n# mutated\n", encoding="utf-8")
        gv_before = self.idx.graph_version()
        self.idx.staleness_report()  # must NOT reindex
        self.assertEqual(self.idx.graph_version(), gv_before)
        # and the graph still serves the (stale) data unchanged
        self.assertIsNotNone(self.idx.find_by_qualname("compute"))

    def test_reindex_clears_staleness(self):
        (self.root / "app.py").write_text(APP + "\n# mutated\n", encoding="utf-8")
        self.assertFalse(self.idx.staleness_report().is_fresh)
        self.idx.index()
        self.assertTrue(self.idx.staleness_report().is_fresh)

    def test_context_compiler_flags_stale_when_asked(self):
        cid = self.idx.find_by_qualname("compute")["symbol_id"]
        self.assertFalse(ContextCompiler(self.idx)
                         .compile(cid, check_staleness=True).stale)
        (self.root / "app.py").write_text(APP + "\n# mutated\n", encoding="utf-8")
        ctx = ContextCompiler(self.idx).compile(cid, check_staleness=True)
        self.assertTrue(ctx.stale)
        self.assertFalse(ctx.verified)  # Law 1: stale is not verification

    def test_context_compiler_default_is_stale_false(self):
        # without check_staleness the probe is skipped (cheap default path)
        cid = self.idx.find_by_qualname("compute")["symbol_id"]
        ctx = ContextCompiler(self.idx).compile(cid)
        self.assertFalse(ctx.stale)

    def test_summary_reports_categories(self):
        (self.root / "app.py").write_text(APP + "\n# x\n", encoding="utf-8")
        (self.root / "test_app.py").unlink()
        r = self.idx.staleness_report()
        self.assertIn("changed=1", r.summary())
        self.assertIn("removed=1", r.summary())


class CodeIntelRetrievalTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        root = Path(self._td.name) / "proj"
        root.mkdir()
        (root / "app.py").write_text(APP, encoding="utf-8")
        self.idx = CodeIndex(root, db_path=Path(self._td.name) / "proj.db")
        self.idx.index()
        self.ret = Retriever(self.idx)

    def tearDown(self):
        self.idx.close()
        self._td.cleanup()

    def test_exact_stage_hits_symbol(self):
        hits = self.ret.search("compute")
        self.assertTrue(any(h.stage == "exact" and h.name == "compute"
                            for h in hits))

    def test_graph_stage_surfaces_neighbors(self):
        hits = self.ret.search("compute")
        # compute CALLS helper_add, and is CALLED BY run -> graph neighbors
        self.assertTrue(any(h.stage == "graph" for h in hits))
        names = {h.name for h in hits if h.stage == "graph"}
        self.assertTrue({"helper_add", "run"} & names)

    def test_lexical_stage_fts5(self):
        self.assertTrue(self.idx._fts_ok)
        hits = self.ret.search("Add two numbers")
        self.assertTrue(any(h.stage == "lexical" and h.name == "helper_add"
                            for h in hits))

    def test_empty_query_returns_nothing(self):
        self.assertEqual(self.ret.search("   "), [])


class CodeIntelContextTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        root = Path(self._td.name) / "proj"
        root.mkdir()
        (root / "app.py").write_text(APP, encoding="utf-8")
        (root / "test_app.py").write_text(TEST_APP, encoding="utf-8")
        self.idx = CodeIndex(root, db_path=Path(self._td.name) / "proj.db")
        self.idx.index()
        self.cc = ContextCompiler(self.idx)

    def tearDown(self):
        self.idx.close()
        self._td.cleanup()

    def test_compiles_target_callers_callees(self):
        cid = self.idx.find_by_qualname("compute")["symbol_id"]
        ctx = self.cc.compile(cid)
        self.assertEqual(ctx.target["name"], "compute")
        self.assertTrue(any(c["name"] == "run" for c in ctx.callers))
        self.assertTrue(any(c["name"] == "helper_add" for c in ctx.callees))

    def test_context_is_evidence_not_verification(self):
        # Law 1: the layer never claims correctness and never calls a model.
        cid = self.idx.find_by_qualname("compute")["symbol_id"]
        ctx = self.cc.compile(cid)
        self.assertFalse(ctx.verified)
        self.assertEqual(ctx.model_calls, 0)
        self.assertEqual(ctx.source, "code_intel")

    def test_unknown_target_returns_empty_context(self):
        ctx = self.cc.compile("S:doesnotexist")
        self.assertEqual(ctx.target, {})
        self.assertEqual(ctx.callers, [])


class CodeIntelSmokeTests(unittest.TestCase):
    def test_run_code_intel_smoke_passes(self):
        self.assertTrue(run_code_intel_smoke()["passed"])


if __name__ == "__main__":
    unittest.main()

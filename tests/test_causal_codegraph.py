"""Tests for Causal Delta x CodeGraph (lola_causal_codegraph).

Deterministic, zero-model: first-divergence localization of an expected
chain against observed per-step statuses, over the CodeGraph (PR #55),
plus the thread's deterministic repair rules (UNRESOLVED_SYMBOL /
MISSING_IMPORT / SAME_FILE_DEFINITION / CHECK_MISMATCH), each a
hypothesis (verified=False, Law 1), and the FAST-CODE reverse lookup
(who calls X, 0 model calls).

Covers the thread's literal scenario (first divergence focuses the chain;
"the GGUF doesn't need to search the entire project"), the sober-failure
invariant (unobserved = UNKNOWN, not-in-graph = unknown, never invented
as a failure), and the repair-hypothesis rule table.
"""
import tempfile
import unittest
from pathlib import Path

from lola_code_intel import CodeIndex
from lola_causal_codegraph import (
    CHECK_ABSENT,
    CHECK_FAIL,
    CHECK_OK,
    CHECK_UNKNOWN,
    CausalCodeGraph,
    run_causal_codegraph_smoke,
)

APP = (
    "import helper\n"
    "def send(x):\n"
    "    '''Send via route.'''\n"
    "    return route(x)\n"
    "def route(x):\n"
    "    '''Route the payload.'''\n"
    "    return x\n"
)
HELPER = (
    "def route(x):\n"
    "    '''Route.'''\n"
    "    return x\n"
)
BROKEN_APP = (
    "def send(x):\n"
    "    '''Send without the helper import.'''\n"
    "    return route(x)\n"
)


def _build(files: dict) -> tuple[tempfile.TemporaryDirectory, CodeIndex]:
    td = tempfile.TemporaryDirectory()
    root = Path(td.name) / "proj"
    root.mkdir(parents=True, exist_ok=True)
    for fn, text in files.items():
        p = root / fn
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    idx = CodeIndex(root, db_path=Path(td.name) / "proj.db")
    idx.index()
    return td, idx


class ChainTraceTests(unittest.TestCase):
    def setUp(self):
        self._td, self.idx = _build({"app.py": APP, "helper.py": HELPER})
        self.ccg = CausalCodeGraph(self.idx)

    def tearDown(self):
        self.idx.close()
        self._td.cleanup()

    def test_no_divergence_is_verified_with_graph_scope(self):
        t = self.ccg.trace_chain(["send", "route"], observed={0: CHECK_OK, 1: CHECK_OK})
        self.assertEqual(t.first_divergence, {"index": -1, "status": "no_divergence"})
        self.assertTrue(t.verified)
        self.assertEqual(t.model_calls, 0)
        self.assertTrue(t.graph_version)  # evidence scope is the graph version

    def test_first_divergence_shape_and_flag(self):
        t = self.ccg.trace_chain(["send", "route"], observed={0: CHECK_OK, 1: CHECK_ABSENT})
        self.assertEqual(t.first_divergence["index"], 1)
        self.assertEqual(t.first_divergence["key"], "route")
        self.assertEqual(t.first_divergence["actual"], CHECK_ABSENT)
        self.assertFalse(t.verified)
        self.assertTrue(t.steps[1].first_divergence)
        self.assertFalse(t.steps[0].first_divergence)

    def test_first_divergence_is_the_first_one(self):
        t = self.ccg.trace_chain(
            ["send", "route"], observed={0: CHECK_FAIL, 1: CHECK_FAIL})
        self.assertEqual(t.first_divergence["index"], 0)
        self.assertTrue(t.steps[0].first_divergence)
        self.assertFalse(t.steps[1].first_divergence)

    def test_unobserved_is_unknown_not_failure(self):
        t = self.ccg.trace_chain(["send", "route"], observed={0: CHECK_OK})
        self.assertEqual(t.steps[1].observed, CHECK_UNKNOWN)
        self.assertEqual(t.first_divergence["status"], "no_divergence")
        self.assertTrue(t.verified)

    def test_not_in_graph_is_unknown_never_failure(self):
        t = self.ccg.trace_chain(["send", "ghost"], observed={0: CHECK_OK, 1: CHECK_FAIL})
        self.assertFalse(t.steps[1].found)
        self.assertEqual(t.first_divergence["index"], 1)
        self.assertIn("UNRESOLVED_SYMBOL", [h.rule for h in t.hypotheses])

    def test_unresolved_tail_lists_not_found_steps_after_divergence(self):
        t = self.ccg.trace_chain(
            ["send", "route", "ghost"],
            observed={0: CHECK_OK, 1: CHECK_ABSENT, 2: CHECK_UNKNOWN})
        self.assertEqual(t.unresolved_tail, ("ghost",))

    def test_observations_accept_name_keys(self):
        t = self.ccg.trace_chain(["send", "route"], observed={"route": CHECK_FAIL})
        self.assertEqual(t.first_divergence["index"], 1)
        self.assertEqual(t.steps[1].observed, CHECK_FAIL)


class RepairRuleTests(unittest.TestCase):
    def _trace(self, files, chain, observed):
        td, idx = _build(files)
        try:
            return CausalCodeGraph(idx).trace_chain(chain, observed=observed)
        finally:
            idx.close()
            td.cleanup()

    def test_hypotheses_are_never_verified(self):
        t = self._trace({"app.py": BROKEN_APP,
                         "route.py": "def route(x):\n    return x\n"},
                        ["send", "route"], {0: CHECK_OK, 1: CHECK_ABSENT})
        self.assertTrue(t.hypotheses)
        self.assertTrue(all(not h.verified for h in t.hypotheses))

    def test_missing_import_cross_file_not_found(self):
        t = self._trace({"app.py": BROKEN_APP,
                         "route.py": "def route(x):\n    return x\n"},
                        ["send", "route"], {0: CHECK_OK, 1: CHECK_ABSENT})
        mi = [h for h in t.hypotheses if h.rule == "MISSING_IMPORT"]
        self.assertEqual(len(mi), 1)
        self.assertEqual(mi[0].required, "route")
        self.assertEqual(mi[0].target, "app.py")

    def test_missing_import_cross_file_found(self):
        t = self._trace({
            "app.py": "def send(x):\n    return compute(x)\n",
            "calc.py": "def compute(x):\n    return x + 1\n"},
            ["send", "compute"], {0: CHECK_OK, 1: CHECK_FAIL})
        self.assertTrue(t.steps[1].found)
        mi = [h for h in t.hypotheses if h.rule == "MISSING_IMPORT"]
        self.assertEqual(len(mi), 1)
        self.assertEqual(mi[0].required, "calc")
        self.assertEqual(mi[0].target, "app.py")

    def test_no_missing_import_when_imported(self):
        t = self._trace({
            "app.py": "import calc\ndef send(x):\n    return compute(x)\n",
            "calc.py": "def compute(x):\n    return x + 1\n"},
            ["send", "compute"], {0: CHECK_OK, 1: CHECK_FAIL})
        self.assertNotIn("MISSING_IMPORT", [h.rule for h in t.hypotheses])
        self.assertTrue(t.hypotheses)  # still a hypothesis, just a different rule

    def test_same_file_definition_rule(self):
        t = self._trace({"app.py": APP},
                        ["send", "route"], {0: CHECK_OK, 1: CHECK_FAIL})
        self.assertIn("SAME_FILE_DEFINITION", [h.rule for h in t.hypotheses])
        self.assertNotIn("MISSING_IMPORT", [h.rule for h in t.hypotheses])

    def test_check_mismatch_fallback_exists(self):
        t = self._trace({"app.py": APP}, ["send"], {"send": CHECK_FAIL})
        self.assertEqual(t.first_divergence["index"], 0)
        self.assertIn("CHECK_MISMATCH", [h.rule for h in t.hypotheses])


class FastCodeTests(unittest.TestCase):
    def setUp(self):
        self._td, self.idx = _build({"app.py": APP, "helper.py": HELPER})
        self.ccg = CausalCodeGraph(self.idx)

    def tearDown(self):
        self.idx.close()
        self._td.cleanup()

    def test_who_calls_zero_model(self):
        wc = self.ccg.who_calls("route")
        self.assertEqual(wc["model_calls"], 0)
        self.assertFalse(wc["verified"])  # a graph observation, not verification
        self.assertTrue(any(c["qualname"] == "send" for c in wc["callers"]))

    def test_who_calls_deterministic_order(self):
        a = self.ccg.who_calls("route")
        b = self.ccg.who_calls("route")
        self.assertEqual(a["callers"], b["callers"])


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self._td, self.idx = _build({
            "app.py": APP,
            "m/core.py": "def core_fn():\n    pass\n",
            "helper.py": HELPER,
        })
        self.ccg = CausalCodeGraph(self.idx)

    def tearDown(self):
        self.idx.close()
        self._td.cleanup()

    def test_name_resolution(self):
        r = self.ccg._resolve("send")
        self.assertTrue(r["found"])
        self.assertEqual(r["qualname"], "send")

    def test_module_stem_resolution(self):
        r = self.ccg._resolve("core")
        self.assertTrue(r["found"])
        self.assertEqual(r["rel_path"], "m/core.py")
        self.assertEqual(r["symbol_id"], "")

    def test_resolution_deterministic_tiebreak(self):
        a = self.ccg._resolve("route")
        b = self.ccg._resolve("route")
        self.assertEqual(a, b)
        # two 'route' symbols (app.py, helper.py): lexicographically smallest
        # rel_path wins -> app.py
        self.assertEqual(a["rel_path"], "app.py")


class SmokeTests(unittest.TestCase):
    def test_smoke_passes(self):
        r = run_causal_codegraph_smoke()
        self.assertTrue(r["passed"], r["failed"])
        self.assertGreaterEqual(r["total"], 12)


if __name__ == "__main__":
    unittest.main()

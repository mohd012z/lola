import unittest
from lola_trace_ledger import TraceEntry
from lola_recoverable_traced_cycle import run_recoverable_traced_cycle

class RecoverableTracedCycleTests(unittest.TestCase):
    def _args(self):
        return dict(records=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":"old"},{"knowledge_id":"k1","version":2,"state":"ACTIVE","supersedes_version":1,"payload":"new"}],snapshot={"k1":1},dependencies={"h1":["k1"]},before={"h1":"A"},after={"h1":"C"},contradictions=0,unknowns=0,trace_id="t1")

    def test_clean_cycle_is_verified(self):
        r=run_recoverable_traced_cycle(**self._args())
        self.assertEqual(r.status,"VERIFIED")
        self.assertFalse(r.quarantine)

    def test_external_tampered_trace_is_quarantined(self):
        clean=run_recoverable_traced_cycle(**self._args())
        e=clean.entries[1]
        tampered=clean.entries[:1]+(TraceEntry(e.trace_id,e.sequence,e.stage,{"tampered":True},e.digest),)+clean.entries[2:]
        r=run_recoverable_traced_cycle(**self._args(),verification_entries=tampered)
        self.assertEqual(r.status,"QUARANTINED")
        self.assertEqual(r.replay_from_sequence,2)
        self.assertFalse(r.execution_authority)

if __name__ == "__main__": unittest.main()

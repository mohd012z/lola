import unittest
from lola_trace_ledger import TraceLedger, TraceEntry
from lola_recovery_consolidation_controller import control_recovery

class RecoveryConsolidationControllerTests(unittest.TestCase):
    def test_clean_verified_trace_can_release_candidate(self):
        ledger=TraceLedger("t1").append("SCAN",{"x":1})
        r=control_recovery(trace_id="t1",entries=ledger.entries,replacement_stages=None,changed_hypotheses=[],unresolved_hypotheses=[],contradictions=0,unknowns=0)
        self.assertEqual(r.status,"RELEASE_CANDIDATE")
        self.assertFalse(r.quarantine)

    def test_tampered_trace_without_recovery_stays_quarantined(self):
        ledger=TraceLedger("t1").append("SCAN",{"x":1})
        e=ledger.entries[0]
        tampered=(TraceEntry(e.trace_id,e.sequence,e.stage,{"x":2},e.digest),)
        r=control_recovery(trace_id="t1",entries=tampered,replacement_stages=None,changed_hypotheses=[],unresolved_hypotheses=[],contradictions=0,unknowns=0)
        self.assertEqual(r.status,"QUARANTINED")
        self.assertEqual(r.reason,"TRACE_MISMATCH")

    def test_recovered_changed_reasoning_requires_recheck(self):
        ledger=TraceLedger("t1").append("SCAN",{"x":1}).append("REPLAY",{"h":"old"})
        e=ledger.entries[1]
        tampered=ledger.entries[:1]+(TraceEntry(e.trace_id,e.sequence,e.stage,{"h":"bad"},e.digest),)
        r=control_recovery(trace_id="t1",entries=tampered,replacement_stages=[("REPLAY",{"h":"new"})],changed_hypotheses=["h1"],unresolved_hypotheses=[],contradictions=0,unknowns=0)
        self.assertEqual(r.status,"RECHECK")
        self.assertTrue(r.quarantine)

if __name__ == "__main__": unittest.main()

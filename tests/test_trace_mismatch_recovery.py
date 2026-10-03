import unittest
from lola_trace_ledger import TraceLedger, TraceEntry
from lola_trace_mismatch_recovery import assess_trace_recovery

class TraceMismatchRecoveryTests(unittest.TestCase):
    def test_valid_trace_needs_no_recovery(self):
        ledger=TraceLedger("t1").append("SCAN",{"x":1})
        r=assess_trace_recovery("t1",ledger.entries)
        self.assertEqual(r.status,"VERIFIED")
        self.assertEqual(r.replay_from_sequence,None)
        self.assertFalse(r.quarantine)

    def test_tampered_trace_is_quarantined_at_first_mismatch(self):
        ledger=TraceLedger("t1").append("SCAN",{"x":1}).append("REPLAY",{"h":"h1"})
        first=ledger.entries[0]
        tampered=(TraceEntry(first.trace_id,first.sequence,first.stage,{"x":2},first.digest),)+ledger.entries[1:]
        r=assess_trace_recovery("t1",tampered)
        self.assertEqual(r.status,"QUARANTINED")
        self.assertEqual(r.replay_from_sequence,1)
        self.assertTrue(r.quarantine)
        self.assertFalse(r.execution_authority)

    def test_later_mismatch_targets_only_divergent_suffix(self):
        ledger=TraceLedger("t1").append("SCAN",{"x":1}).append("REPLAY",{"h":"h1"})
        second=ledger.entries[1]
        tampered=ledger.entries[:1]+(TraceEntry(second.trace_id,second.sequence,second.stage,{"h":"h2"},second.digest),)
        r=assess_trace_recovery("t1",tampered)
        self.assertEqual(r.replay_from_sequence,2)

if __name__ == "__main__": unittest.main()

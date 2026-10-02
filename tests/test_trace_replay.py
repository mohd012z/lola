import unittest
from lola_trace_ledger import TraceLedger
from lola_trace_replay import verify_trace

class TraceReplayTests(unittest.TestCase):
    def test_valid_trace_verifies(self):
        ledger=TraceLedger("t1").append("SCAN",{"x":1}).append("REPLAY",{"h":["h1"]})
        r=verify_trace("t1",ledger.entries)
        self.assertTrue(r.valid)
        self.assertEqual(r.status,"VERIFIED")

    def test_modified_payload_is_detected(self):
        ledger=TraceLedger("t1").append("SCAN",{"x":1})
        e=ledger.entries[0]
        tampered=[type(e)(e.trace_id,e.sequence,e.stage,{"x":2},e.digest)]
        r=verify_trace("t1",tampered)
        self.assertFalse(r.valid)
        self.assertEqual(r.status,"MISMATCH")

    def test_wrong_trace_id_is_rejected(self):
        ledger=TraceLedger("t1").append("SCAN",{})
        self.assertFalse(verify_trace("other",ledger.entries).valid)

if __name__ == "__main__": unittest.main()

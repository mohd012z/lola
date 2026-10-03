import unittest
from lola_trace_ledger import TraceLedger

class TraceLedgerTests(unittest.TestCase):
    def test_stage_order_is_preserved(self):
        ledger=TraceLedger("t1").append("MEMORY_SCAN",{"status":"CURRENT"}).append("REPLAY",{"count":1})
        self.assertEqual(tuple(e.stage for e in ledger.entries),("MEMORY_SCAN","REPLAY"))
        self.assertEqual(tuple(e.sequence for e in ledger.entries),(1,2))

    def test_same_inputs_produce_same_digest(self):
        a=TraceLedger("t1").append("A",{"x":1,"y":2})
        b=TraceLedger("t1").append("A",{"y":2,"x":1})
        self.assertEqual(a.entries[0].digest,b.entries[0].digest)

    def test_trace_id_is_required(self):
        with self.assertRaises(ValueError): TraceLedger("")

if __name__ == "__main__": unittest.main()

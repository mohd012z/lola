import unittest
from lola_trace_ledger import TraceLedger
from lola_suffix_recovery_executor import recover_trace_suffix

class SuffixRecoveryExecutorTests(unittest.TestCase):
    def test_preserves_verified_prefix_and_rebuilds_suffix(self):
        original=TraceLedger("t1").append("SCAN",{"x":1}).append("REPLAY",{"h":"old"}).append("FEEDBACK",{"status":"old"})
        r=recover_trace_suffix("t1",original.entries,2,[("REPLAY",{"h":"new"}),("FEEDBACK",{"status":"new"})])
        self.assertEqual(r.entries[0],original.entries[0])
        self.assertNotEqual(r.entries[1].digest,original.entries[1].digest)
        self.assertEqual(r.verification.status,"VERIFIED")
        self.assertEqual(r.status,"RECOVERED")
        self.assertFalse(r.execution_authority)

    def test_invalid_replay_start_is_rejected(self):
        original=TraceLedger("t1").append("SCAN",{})
        with self.assertRaises(ValueError): recover_trace_suffix("t1",original.entries,3,[])

    def test_recovery_from_first_stage_rebuilds_all(self):
        original=TraceLedger("t1").append("SCAN",{"x":1})
        r=recover_trace_suffix("t1",original.entries,1,[("SCAN",{"x":2})])
        self.assertEqual(r.entries[0].payload,{"x":2})
        self.assertEqual(r.verification.status,"VERIFIED")

if __name__ == "__main__": unittest.main()

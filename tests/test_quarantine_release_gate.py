import unittest
from lola_quarantine_release_gate import assess_quarantine_release

class QuarantineReleaseGateTests(unittest.TestCase):
    def test_verified_stable_recovery_can_release(self):
        r=assess_quarantine_release(trace_verified=True,changed_hypotheses=[],unresolved_hypotheses=[],contradictions=0,unknowns=0)
        self.assertEqual(r.status,"RELEASE_CANDIDATE")
        self.assertFalse(r.quarantine)
        self.assertFalse(r.execution_authority)

    def test_changed_reasoning_requires_l5_recheck(self):
        r=assess_quarantine_release(trace_verified=True,changed_hypotheses=["h1"],unresolved_hypotheses=[],contradictions=0,unknowns=0)
        self.assertEqual(r.status,"RECHECK")
        self.assertTrue(r.quarantine)

    def test_unverified_trace_stays_quarantined(self):
        r=assess_quarantine_release(trace_verified=False,changed_hypotheses=[],unresolved_hypotheses=[],contradictions=0,unknowns=0)
        self.assertEqual(r.status,"QUARANTINED")

    def test_contradiction_has_priority(self):
        r=assess_quarantine_release(trace_verified=True,changed_hypotheses=[],unresolved_hypotheses=[],contradictions=1,unknowns=0)
        self.assertEqual(r.recommendation,"RESOLVE_CONTRADICTION")
        self.assertTrue(r.quarantine)

if __name__ == "__main__": unittest.main()

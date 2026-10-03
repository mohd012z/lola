import unittest
from lola_revision_cycle import run_revision_cycle

class RevisionCycleTests(unittest.TestCase):
    def test_failed_replay_produces_revision_and_quarantine(self):
        r=run_revision_cycle(
            candidate_id="c1", assumptions=["a1","a2"], invalid_assumption_ids=["a2"],
            supporting_evidence_ids=["e1"], counterexample_evidence_ids=["bad"],
            evidence_count=3, independent_origins=2, contradictions=0, unknowns=0,
            failed_replays=1, recurrence=3, counterexamples=1, transfer_supported=True)
        self.assertEqual(r.revision_status,"REVISED")
        self.assertEqual(r.rollback_action,"QUARANTINE")
        self.assertFalse(r.execution_authority)

    def test_clean_state_does_not_invent_revision(self):
        r=run_revision_cycle(
            candidate_id="c1", assumptions=["a1"], invalid_assumption_ids=[],
            supporting_evidence_ids=["e1","e2"], counterexample_evidence_ids=[],
            evidence_count=3, independent_origins=2, contradictions=0, unknowns=0,
            failed_replays=0, recurrence=3, counterexamples=0, transfer_supported=True)
        self.assertEqual(r.revision_status,"NOT_REQUIRED")
        self.assertEqual(r.cognitive_status,"CANDIDATE")

if __name__ == "__main__": unittest.main()

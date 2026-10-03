import unittest

from lola_cognitive_transaction import build_cognitive_transaction


class CognitiveTransactionTests(unittest.TestCase):
    def test_expected_and_observed_delta_are_kept_separate(self):
        tx = build_cognitive_transaction(
            transaction_id="tx1",
            state_before={"unknowns": ["cause"], "status": "OPEN"},
            action="inspect dependency",
            expected_delta={"unknowns_removed": ["cause"]},
            state_after={"unknowns": [], "status": "OPEN"},
            evidence_ids=["e1"],
        )
        self.assertEqual(tx.expected_delta, {"unknowns_removed": ["cause"]})
        self.assertEqual(tx.observed_delta["unknowns_removed"], ("cause",))
        self.assertEqual(tx.evidence_ids, ("e1",))

    def test_prediction_mismatch_is_explicit(self):
        tx = build_cognitive_transaction(
            transaction_id="tx2",
            state_before={"unknowns": ["cause"], "status": "OPEN"},
            action="retry",
            expected_delta={"status_changed_to": "RESOLVED"},
            state_after={"unknowns": ["cause"], "status": "OPEN"},
        )
        self.assertTrue(tx.prediction_error)
        self.assertFalse(tx.progress_made)

    def test_matching_prediction_has_no_prediction_error(self):
        tx = build_cognitive_transaction(
            transaction_id="tx3",
            state_before={"unknowns": ["cause"], "status": "OPEN"},
            action="inspect",
            expected_delta={"unknowns_removed": ["cause"]},
            state_after={"unknowns": [], "status": "OPEN"},
        )
        self.assertFalse(tx.prediction_error)
        self.assertTrue(tx.progress_made)

    def test_zero_delta_is_detected_as_no_progress(self):
        state = {"unknowns": ["cause"], "status": "OPEN"}
        tx = build_cognitive_transaction(
            transaction_id="tx4",
            state_before=state,
            action="retry",
            expected_delta={},
            state_after=dict(state),
        )
        self.assertEqual(tx.observed_delta, {})
        self.assertFalse(tx.progress_made)


if __name__ == "__main__":
    unittest.main()

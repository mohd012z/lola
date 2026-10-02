import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from lola import main
from lola_prospective_prereg import (
    load_preregistration,
    validate_preregistration,
)


class ProspectiveTransferPreregistrationTests(unittest.TestCase):
    def test_sealed_registration_reports_awaiting_holdout_not_success(self):
        registration = load_preregistration()
        result = validate_preregistration(registration)

        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "SEALED_AWAITING_HOLDOUT")
        self.assertEqual(result["phase"], "PREREGISTRATION")
        self.assertEqual(result["hypothesis"], "preflight_validity")
        self.assertEqual(result["evaluator_blob_sha"], "5274be28fe602edf18aeca1a2c287d0ac2c22f8b")
        self.assertEqual(result["model_id"], "kernel-historical-inspector-v2")
        self.assertEqual(result["hardware_id"], "frozen-fixture-runtime")
        self.assertFalse(result["holdout_revealed"])
        self.assertFalse(result["blind_holdout_claim"])
        self.assertFalse(result["prospective_claim"])
        self.assertFalse(result["production_world_claim"])

    def test_contract_tampering_breaks_seal(self):
        registration = load_preregistration()
        tampered = copy.deepcopy(registration)
        tampered["evaluation_contract"]["minimum_action_delta"] = -2

        result = validate_preregistration(tampered)

        self.assertFalse(result["valid"])
        self.assertEqual(result["status"], "INVALID_SEAL")
        self.assertIn("contract_digest_mismatch", result["reasons"])
        self.assertFalse(result["prospective_claim"])

    def test_selection_rule_cannot_target_known_outcome(self):
        registration = load_preregistration()
        tampered = copy.deepcopy(registration)
        tampered["holdout_selection"]["known_outcome_allowed"] = True
        tampered["seal_sha256"] = tampered["computed_test_only_seal"]

        result = validate_preregistration(tampered)

        self.assertFalse(result["valid"])
        self.assertIn("known_outcome_selection_forbidden", result["reasons"])
        self.assertFalse(result["prospective_claim"])

    def test_cli_validates_registration_without_claiming_result(self):
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["lola.py", "--prospective-transfer-prereg"]):
            with redirect_stdout(stdout):
                rc = main()

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["status"], "SEALED_AWAITING_HOLDOUT")
        self.assertFalse(payload["prospective_claim"])


if __name__ == "__main__":
    unittest.main()

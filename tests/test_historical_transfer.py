import unittest

from lola_historical_transfer import (
    load_historical_transfer_fixture,
    run_historical_transfer_suite,
)


class HistoricalTransferTests(unittest.TestCase):
    def test_fixture_pins_two_training_origins_and_one_distinct_holdout(self):
        fixture = load_historical_transfer_fixture()

        self.assertEqual(fixture["schema_version"], "historical-transfer-v2")
        self.assertEqual(len(fixture["training_incidents"]), 2)
        self.assertEqual(
            {item["origin_domain"] for item in fixture["training_incidents"]},
            {"powershell-parser", "python-parser"},
        )
        self.assertEqual(fixture["holdout_incident"]["origin_domain"], "semgrep-yaml-parser")
        self.assertFalse(fixture["holdout_incident"]["blind_holdout"])
        self.assertEqual(
            fixture["training_incidents"][0]["source"]["fix_sha"],
            "475d5cb2487334b282aa0b7616258f36e769c35d",
        )
        self.assertEqual(
            fixture["training_incidents"][1]["source"]["fix_sha"],
            "79c62b3cfbc002d800df09526c0451101758849a",
        )
        self.assertEqual(
            fixture["holdout_incident"]["source"]["fix_sha"],
            "6b1929f587050e378bfb4ae86817d7c9a9370e10",
        )

    def test_independent_historical_incidents_transfer_preflight_priority_to_holdout(self):
        result = run_historical_transfer_suite()

        self.assertEqual(result["mode"], "HISTORICAL-TRANSFER")
        self.assertEqual(result["abstract_failure_role"], "preflight_validity")
        self.assertEqual(result["compiled"]["effective_independent_origins"], 2)
        self.assertTrue(result["governance"]["promotable"])

        for incident in result["training_replay"]:
            self.assertFalse(incident["before_valid"])
            self.assertTrue(incident["after_valid"])

        holdout = result["holdout"]
        self.assertFalse(holdout["before_valid"])
        self.assertTrue(holdout["after_valid"])
        self.assertEqual(holdout["transfer_distance"], 3)
        self.assertEqual(holdout["baseline"]["actions"], 4)
        self.assertEqual(holdout["learned"]["actions"], 1)
        self.assertTrue(holdout["growth"]["passed"])
        self.assertEqual(holdout["learned"]["regression_failures"], 0)

        self.assertTrue(result["historical_transfer_claim"])
        self.assertFalse(result["blind_holdout_claim"])
        self.assertFalse(result["production_world_claim"])

    def test_counterexample_blocks_transfer_and_removes_downshift(self):
        result = run_historical_transfer_suite(counterexample=True)

        self.assertFalse(result["governance"]["promotable"])
        self.assertEqual(result["governance"]["reason"], "counterexamples_unresolved")
        self.assertEqual(
            result["holdout"]["learned"]["actions"],
            result["holdout"]["baseline"]["actions"],
        )
        self.assertFalse(result["holdout"]["growth"]["passed"])
        self.assertFalse(result["historical_transfer_claim"])


if __name__ == "__main__":
    unittest.main()

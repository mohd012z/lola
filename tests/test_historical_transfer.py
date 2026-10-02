import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from lola import main
from lola_historical_transfer import (
    build_training_episodes,
    run_historical_transfer_suite,
)


class HistoricalTransferTests(unittest.TestCase):
    def test_cross_format_replay_measures_governed_transfer(self):
        result = run_historical_transfer_suite()

        self.assertEqual(result["mode"], "HISTORICAL-TRANSFER-RETROSPECTIVE")
        self.assertTrue(result["historical_transfer_claim"])
        self.assertFalse(result["blind_holdout_claim"])
        self.assertFalse(result["production_world_claim"])
        self.assertFalse(result["external_ai_used"])

        self.assertEqual(result["training"]["effective_independent_origins"], 2)
        self.assertEqual(
            set(result["training"]["validator_kinds"]),
            {"powershell_parser", "python_ast"},
        )
        self.assertTrue(result["governance"]["promotable"])
        self.assertFalse(result["governance"]["execution_authority"])

        holdout = result["holdout"]
        self.assertEqual(holdout["validator_kind"], "semgrep_rule_schema")
        self.assertTrue(holdout["before"]["known_defect_detected"])
        self.assertFalse(holdout["after"]["known_defect_detected"])
        self.assertEqual(holdout["baseline_actions"], 4)
        self.assertEqual(holdout["learned_actions"], 1)
        self.assertEqual(holdout["baseline_intellectual_level"], 4)
        self.assertEqual(holdout["learned_intellectual_level"], 1)
        self.assertTrue(holdout["verified"])
        self.assertFalse(holdout["false_solved"])

    def test_shared_origin_training_cannot_claim_transfer(self):
        episodes = list(build_training_episodes())
        episodes[1] = {
            **episodes[1],
            "origin_domains": episodes[0]["origin_domains"],
        }

        result = run_historical_transfer_suite(episodes=episodes)

        self.assertFalse(result["historical_transfer_claim"])
        self.assertFalse(result["governance"]["promotable"])
        self.assertEqual(result["holdout"]["learned_actions"], result["holdout"]["baseline_actions"])
        self.assertEqual(result["holdout"]["learned_intellectual_level"], 4)

    def test_cli_runs_retrospective_historical_transfer_without_target(self):
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["lola.py", "--historical-transfer-benchmark"]):
            with redirect_stdout(stdout):
                rc = main()

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["mode"], "HISTORICAL-TRANSFER-RETROSPECTIVE")
        self.assertTrue(payload["historical_transfer_claim"])
        self.assertFalse(payload["blind_holdout_claim"])
        self.assertFalse(payload["production_world_claim"])


if __name__ == "__main__":
    unittest.main()

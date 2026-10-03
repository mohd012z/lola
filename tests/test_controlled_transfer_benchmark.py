import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from lola import main
from lola_controlled_transfer_benchmark import (
    build_verified_learning_episodes,
    run_controlled_transfer_suite,
)


class ControlledTransferBenchmarkTests(unittest.TestCase):
    def test_t2_and_t3_transfer_downshift_after_governed_learning(self):
        result = run_controlled_transfer_suite()

        self.assertTrue(result["compiled"]["effective_independent_origins"] >= 2)
        self.assertEqual(result["governance"]["reason"], "governance_passed")
        self.assertTrue(result["governance"]["promotable"])
        self.assertFalse(result["governance"]["execution_authority"])

        trials = {item["transfer_distance"]: item for item in result["trials"]}
        self.assertIn(2, trials)
        self.assertIn(3, trials)

        for distance in (2, 3):
            trial = trials[distance]
            self.assertTrue(trial["growth"]["passed"])
            self.assertEqual(trial["growth"]["status"], "SYSTEM_INTELLIGENCE_GAIN")
            self.assertLess(trial["learned"]["actions"], trial["baseline"]["actions"])
            self.assertLess(trial["learned"]["intellectual_level"], trial["baseline"]["intellectual_level"])
            self.assertTrue(trial["baseline"]["verified"])
            self.assertTrue(trial["learned"]["verified"])
            self.assertFalse(trial["learned"]["false_solved"])
            self.assertEqual(trial["learned"]["regression_failures"], 0)

        self.assertTrue(result["controlled_empirical_claim"])
        self.assertFalse(result["production_world_claim"])

    def test_counterexample_blocks_promotion_and_downshift(self):
        episodes = list(build_verified_learning_episodes())
        episodes.append(
            {
                "episode_id": "counterexample-1",
                "context": {
                    "family": "causal-pipeline-debug",
                    "abstract_failure_role": "artifact",
                },
                "origin_domains": ("independent-c",),
                "outcome": "FALSIFIED",
            }
        )

        result = run_controlled_transfer_suite(episodes=episodes)
        self.assertFalse(result["governance"]["promotable"])
        self.assertEqual(result["governance"]["reason"], "counterexamples_unresolved")

        for trial in result["trials"]:
            self.assertFalse(trial["growth"]["passed"])
            self.assertIn("no_intellectual_downshift", trial["growth"]["reasons"])
            self.assertEqual(trial["learned"]["actions"], trial["baseline"]["actions"])

    def test_cli_runs_controlled_transfer_suite_without_target(self):
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["lola.py", "--controlled-transfer-benchmark"]):
            with redirect_stdout(stdout):
                rc = main()

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["mode"], "CONTROLLED-EMPIRICAL")
        self.assertTrue(payload["controlled_empirical_claim"])
        self.assertFalse(payload["production_world_claim"])


if __name__ == "__main__":
    unittest.main()

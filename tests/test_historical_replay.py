import unittest

from lola_historical_replay import (
    load_scanner_cwd_fixture,
    run_scanner_cwd_historical_replay,
)


class HistoricalReplayTests(unittest.TestCase):
    def test_real_scanner_cwd_incident_replays_before_and_after_fix(self):
        fixture = load_scanner_cwd_fixture()
        result = run_scanner_cwd_historical_replay(fixture)

        self.assertEqual(result["source"]["before_sha"], "66d9bd02d5b9ed195aaccf6d922b8b08d522505e")
        self.assertEqual(result["source"]["fix_sha"], "6b1929f587050e378bfb4ae86817d7c9a9370e10")
        self.assertTrue(result["before"]["known_defect_detected"])
        self.assertFalse(result["after"]["known_defect_detected"])
        self.assertGreaterEqual(result["before"]["cwd_relative_helper_count"], 3)
        self.assertEqual(result["after"]["cwd_relative_helper_count"], 0)
        self.assertFalse(result["before"]["config_script_root_fallback"])
        self.assertTrue(result["after"]["config_script_root_fallback"])
        self.assertTrue(result["historical_replay_claim"])
        self.assertFalse(result["transfer_claim"])
        self.assertFalse(result["production_world_claim"])

    def test_fixture_is_provenance_pinned(self):
        fixture = load_scanner_cwd_fixture()
        self.assertEqual(fixture["source"]["repository"], "mohd012z/lola")
        self.assertEqual(fixture["source"]["path"], "scan-security.ps1")
        self.assertEqual(fixture["source"]["before_blob_sha"], "f433e44786574a5fa3d9f54d2812f7cc48059af5")
        self.assertEqual(fixture["source"]["fixed_blob_sha"], "9ace16e38bfce25668558d9f5d3e6a5cd612e032")


if __name__ == "__main__":
    unittest.main()

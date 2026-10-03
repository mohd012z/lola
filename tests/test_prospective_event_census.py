import hashlib
import json
import unittest

import lola_prospective_event_census as census_module
from lola_prospective_result import ANCHOR_SHA, PREREGISTRATION_SEAL, REGISTRATION_ID


def digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ProspectiveEventCensusGenerationTests(unittest.TestCase):
    def _runs(self):
        return [
            {
                "id": 5000,
                "run_attempt": 1,
                "name": "Lola Code Doctor",
                "head_sha": "2" * 40,
                "status": "completed",
                "conclusion": "failure",
                "run_started_at": "2026-10-02T11:00:00Z",
                "updated_at": "2026-10-02T11:01:00Z",
                "url": "https://api.github.com/repos/example/lola/actions/runs/5000",
            },
            {
                "id": 4500,
                "run_attempt": 1,
                "name": "Prospective holdout observer",
                "head_sha": "4" * 40,
                "status": "completed",
                "conclusion": "failure",
                "run_started_at": "2026-10-02T10:30:00Z",
                "updated_at": "2026-10-02T10:31:00Z",
                "url": "https://api.github.com/repos/example/lola/actions/runs/4500",
            },
            {
                "id": 4242,
                "run_attempt": 1,
                "name": "Toolchain smoke check",
                "head_sha": "1" * 40,
                "status": "completed",
                "conclusion": "failure",
                "run_started_at": "2026-10-02T10:00:00Z",
                "updated_at": "2026-10-02T10:01:00Z",
                "url": "https://api.github.com/repos/example/lola/actions/runs/4242",
            },
            {
                "id": 3000,
                "run_attempt": 1,
                "name": "Lola Bot Health",
                "head_sha": "3" * 40,
                "status": "completed",
                "conclusion": "success",
                "run_started_at": "2026-10-02T09:00:00Z",
                "updated_at": "2026-10-02T09:01:00Z",
                "url": "https://api.github.com/repos/example/lola/actions/runs/3000",
            },
        ]

    def test_builder_exists_and_orders_reviewable_history_through_candidate(self):
        builder = getattr(census_module, "build_event_census", None)
        self.assertTrue(callable(builder), "build_event_census must exist")

        value = builder(
            self._runs(),
            candidate_run_id=5000,
            candidate_run_attempt=1,
            history_complete=True,
            trust_post_anchor_flag=True,
        )

        self.assertEqual(value["schema_version"], "prospective-event-census-v1")
        self.assertEqual(value["registration_id"], REGISTRATION_ID)
        self.assertEqual(value["preregistration_anchor_sha"], ANCHOR_SHA)
        self.assertEqual(value["preregistration_seal_sha256"], PREREGISTRATION_SEAL)
        self.assertTrue(value["history_complete_through_candidate"])
        self.assertEqual([event["run_id"] for event in value["ordered_events"]], [4242, 5000])
        self.assertTrue(all(event["git_ancestry_verified"] for event in value["ordered_events"]))
        self.assertEqual(value["candidate_event_key"], value["ordered_events"][-1]["event_key"])
        self.assertNotIn("prior_event_verdicts", value)
        self.assertRegex(value["event_census_digest_sha256"], r"^[0-9a-f]{64}$")

    def test_builder_rejects_incomplete_history(self):
        builder = getattr(census_module, "build_event_census", None)
        self.assertTrue(callable(builder), "build_event_census must exist")
        with self.assertRaises(ValueError):
            builder(
                self._runs(),
                candidate_run_id=5000,
                candidate_run_attempt=1,
                history_complete=False,
                trust_post_anchor_flag=True,
            )

    def test_census_digest_detects_tampering(self):
        builder = getattr(census_module, "build_event_census", None)
        self.assertTrue(callable(builder), "build_event_census must exist")
        value = builder(
            self._runs(),
            candidate_run_id=5000,
            candidate_run_attempt=1,
            history_complete=True,
            trust_post_anchor_flag=True,
        )
        original = value["event_census_digest_sha256"]
        value["ordered_events"][0]["run_id"] = 9999
        unsigned = dict(value)
        unsigned.pop("event_census_digest_sha256")
        self.assertNotEqual(digest(unsigned), original)


if __name__ == "__main__":
    unittest.main()

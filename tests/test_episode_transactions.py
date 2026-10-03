import unittest

from lola_agent_episode import build_agent_episode


class EpisodeTransactionTests(unittest.TestCase):
    def _event(self, eid, topic, payload, ts):
        return {
            "id": eid,
            "task_id": "t1",
            "trace_id": "tr",
            "span_id": eid,
            "parent_span_id": "",
            "topic": topic,
            "timestamp": ts,
            "payload": {"agent_id": "build", **payload},
        }

    def test_decision_and_result_compile_to_cognitive_transaction(self):
        events = [
            self._event(
                "1",
                "agent.decision",
                {
                    "decision_id": "d1",
                    "selected_action": "inspect dependency",
                    "unknowns": ["cause"],
                    "state_before": {"status": "BLOCKED", "unknowns": ["cause"]},
                    "expected_delta": {"unknowns_removed": ["cause"]},
                },
                "2026-10-02T00:00:00+00:00",
            ),
            self._event(
                "2",
                "agent.decision.result",
                {
                    "decision_id": "d1",
                    "state_after": {"status": "BLOCKED", "unknowns": []},
                    "evidence_ids": ["e2", "e2"],
                },
                "2026-10-02T00:00:01+00:00",
            ),
        ]
        episode = build_agent_episode(events, "build", "tr")
        self.assertEqual(len(episode.transactions), 1)
        tx = episode.transactions[0]
        self.assertEqual(tx.transaction_id, "d1")
        self.assertEqual(tx.action, "inspect dependency")
        self.assertEqual(tx.observed_delta["unknowns_removed"], ("cause",))
        self.assertFalse(tx.prediction_error)
        self.assertEqual(tx.evidence_ids, ("e2",))
        self.assertFalse(tx.verification_authority)

    def test_unresolved_decision_does_not_create_transaction(self):
        events = [
            self._event(
                "1",
                "agent.decision",
                {
                    "decision_id": "d1",
                    "selected_action": "inspect",
                    "state_before": {"unknowns": ["cause"]},
                    "expected_delta": {"unknowns_removed": ["cause"]},
                },
                "2026-10-02T00:00:00+00:00",
            )
        ]
        episode = build_agent_episode(events, "build", "tr")
        self.assertEqual(episode.transactions, ())
        self.assertEqual(episode.unresolved_decision_ids, ("d1",))


if __name__ == "__main__":
    unittest.main()

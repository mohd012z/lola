import unittest

from lola_agent_episode import build_agent_episode


class AgentEpisodeTests(unittest.TestCase):
    def _event(self, eid, topic, payload, *, agent="build", trace="tr", ts="2026-10-02T00:00:00+00:00"):
        return {"id": eid, "task_id": "t1", "trace_id": trace, "span_id": eid, "parent_span_id": "", "topic": topic, "timestamp": ts, "payload": {"agent_id": agent, **payload}}

    def test_decision_snapshot_and_result_are_separate(self):
        events = [
            self._event("1", "agent.decision", {"decision_id":"d1","agent_role":"build","known_evidence_ids":["e1"],"active_hypothesis_ids":["h1"],"unknowns":["cause"],"alternatives":["inspect","retry"],"selected_action":"inspect","expected_information_gain":1,"expected_cost":2}),
            self._event("2", "agent.decision.result", {"decision_id":"d1","actual_information_gain":2,"actual_cost":3,"result_event_ids":["r1"],"revision_triggered":True}, ts="2026-10-02T00:00:01+00:00"),
        ]
        ep = build_agent_episode(events, "build", "tr")
        self.assertEqual(ep.decisions[0].known_evidence_ids, ("e1",))
        self.assertEqual(ep.decisions[0].unknowns_before, ("cause",))
        self.assertEqual(ep.decision_results[0].actual_information_gain, 2)
        self.assertEqual(ep.decisions[0].expected_information_gain, 1)

    def test_handoff_preserves_ancestry(self):
        ep = build_agent_episode([self._event("1", "agent.handoff", {"handoff_id":"x","parent_agent":"kernel","child_agent":"build","requested_capability":"compile","inherited_evidence_ids":["e1","e2"],"inherited_assumptions":["a1"],"unresolved_unknowns":["u1"]})], "build", "tr")
        self.assertEqual(ep.handoffs[0].parent_agent, "kernel")
        self.assertEqual(ep.handoffs[0].inherited_evidence_ids, ("e1","e2"))

    def test_filters_foreign_agent_and_trace(self):
        events = [self._event("1", "agent.failure", {"reason":"mine"}), self._event("2", "agent.failure", {"reason":"other"}, agent="repo"), self._event("3", "agent.failure", {"reason":"trace"}, trace="other")]
        ep = build_agent_episode(events, "build", "tr")
        self.assertEqual([e["id"] for e in ep.events], ["1"])

    def test_agent_complete_cannot_self_verify(self):
        ep = build_agent_episode([self._event("1", "agent.complete", {"result":"done"})], "build", "tr")
        self.assertNotEqual(ep.outcome, "VERIFIED")

    def test_independent_verification_can_verify(self):
        events = [
            self._event("1", "agent.complete", {"result":"done"}),
            {"id":"2","task_id":"t1","trace_id":"tr","span_id":"v","parent_span_id":"","topic":"cognitive.verification","timestamp":"2026-10-02T00:00:01+00:00","payload":{"agent_id":"kernel","target_agent_id":"build","verified":True,"evidence_ids":["e1","e2"]}},
        ]
        ep = build_agent_episode(events, "build", "tr")
        self.assertEqual(ep.outcome, "VERIFIED")
        self.assertEqual(ep.verification_evidence_ids, ("e1","e2"))

    def test_failure_recovery_chain_is_ordered(self):
        events = [self._event("1", "agent.failure", {"reason":"compile"}), self._event("2", "agent.recovery", {"failure_event_id":"1","action":"fix"}, ts="2026-10-02T00:00:01+00:00")]
        ep = build_agent_episode(events, "build", "tr")
        self.assertEqual(ep.failures[0]["id"], "1")
        self.assertEqual(ep.recoveries[0]["payload"]["failure_event_id"], "1")

    def test_unresolved_decision_is_partial(self):
        ep = build_agent_episode([self._event("1", "agent.decision", {"decision_id":"d1","alternatives":["a"],"selected_action":"a"})], "build", "tr")
        self.assertEqual(ep.outcome, "PARTIAL")
        self.assertEqual(ep.unresolved_decision_ids, ("d1",))


if __name__ == "__main__":
    unittest.main()

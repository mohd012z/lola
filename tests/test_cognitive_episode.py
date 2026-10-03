import unittest

from lola_cognitive_episode import build_episode, compare_prediction


class EpisodeEngineTests(unittest.TestCase):
    def test_exact_prediction_match(self):
        delta = compare_prediction({"build.status": "PASS"}, {"build.status": "PASS"})
        self.assertTrue(delta.matched)
        self.assertEqual(delta.differences, {})

    def test_prediction_mismatch_is_structured(self):
        delta = compare_prediction({"build.status": "PASS"}, {"build.status": "FAIL"})
        self.assertFalse(delta.matched)
        self.assertEqual(delta.differences["build.status"]["expected"], "PASS")
        self.assertEqual(delta.differences["build.status"]["actual"], "FAIL")

    def test_episode_filters_trace_and_reconstructs_causal_sequence(self):
        events = [
            {"id":"1","task_id":"t","trace_id":"tr","span_id":"s1","parent_span_id":"","kind":"query","topic":"cognitive.prediction","timestamp":"2026-10-02T00:00:00+00:00","payload":{"hypothesis_id":"h1","expected":{"build.status":"PASS"}}},
            {"id":"2","task_id":"t","trace_id":"other","span_id":"x","parent_span_id":"","kind":"result","topic":"cognitive.actual","timestamp":"2026-10-02T00:00:01+00:00","payload":{"actual":{"build.status":"FAIL"}}},
            {"id":"3","task_id":"t","trace_id":"tr","span_id":"s2","parent_span_id":"s1","kind":"result","topic":"cognitive.actual","timestamp":"2026-10-02T00:00:02+00:00","payload":{"hypothesis_id":"h1","actual":{"build.status":"PASS"}}},
            {"id":"4","task_id":"t","trace_id":"tr","span_id":"s3","parent_span_id":"s2","kind":"evidence","topic":"cognitive.verification","timestamp":"2026-10-02T00:00:03+00:00","payload":{"hypothesis_id":"h1","verified":True,"evidence_ids":["e1","e2"]}},
        ]
        episode = build_episode(events, "tr")
        self.assertEqual([e["id"] for e in episode.events], ["1","3","4"])
        self.assertEqual(episode.outcome, "VERIFIED")
        self.assertEqual(len(episode.prediction_deltas), 1)
        self.assertTrue(episode.prediction_deltas[0].matched)
        self.assertEqual(episode.supporting_evidence_ids, ("e1","e2"))

    def test_unresolved_prediction_is_partial(self):
        events = [{"id":"1","task_id":"t","trace_id":"tr","span_id":"s1","parent_span_id":"","kind":"query","topic":"cognitive.prediction","timestamp":"2026-10-02T00:00:00+00:00","payload":{"hypothesis_id":"h1","expected":{"x.y":1}}}]
        episode = build_episode(events, "tr")
        self.assertEqual(episode.outcome, "PARTIAL")
        self.assertEqual(episode.unresolved_predictions, ("h1",))

    def test_failed_verification_is_not_verified(self):
        events = [
            {"id":"1","task_id":"t","trace_id":"tr","span_id":"s1","parent_span_id":"","kind":"evidence","topic":"cognitive.verification","timestamp":"2026-10-02T00:00:00+00:00","payload":{"hypothesis_id":"h1","verified":False,"reason":"validator_failed"}}
        ]
        episode = build_episode(events, "tr")
        self.assertEqual(episode.outcome, "FAILED")


if __name__ == "__main__":
    unittest.main()

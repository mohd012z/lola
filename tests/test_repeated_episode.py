import unittest
from lola_repeated_episode import context_fingerprint, analyze_repeated_agent_episodes


class RepeatedAgentEpisodeTests(unittest.TestCase):
    def test_context_fingerprint_is_order_independent(self):
        a = context_fingerprint({"domain":"build","failure_class":"compile","constraints":["offline","ci"]})
        b = context_fingerprint({"constraints":["ci","offline"],"failure_class":"compile","domain":"build"})
        self.assertEqual(a, b)

    def test_same_origin_recurrence_does_not_inflate_independence(self):
        episodes = [
            {"episode_id":"a","context":{"domain":"build"},"outcome":"VERIFIED","origin_domains":["artifact:x"]},
            {"episode_id":"b","context":{"domain":"build"},"outcome":"VERIFIED","origin_domains":["artifact:x"]},
            {"episode_id":"c","context":{"domain":"build"},"outcome":"VERIFIED","origin_domains":["runtime:y"]},
        ]
        patterns = analyze_repeated_agent_episodes(episodes)
        self.assertEqual(patterns[0].episode_count, 3)
        self.assertEqual(patterns[0].effective_independent_origins, 2)

    def test_repeated_failures_create_failure_pattern(self):
        eps = [{"episode_id":str(i),"context":{"domain":"x"},"outcome":"FAILED","origin_domains":[f"o{i}"]} for i in range(2)]
        self.assertEqual(analyze_repeated_agent_episodes(eps)[0].pattern_type, "FAILURE_PATTERN")

    def test_recovery_pattern_is_detected(self):
        eps = [{"episode_id":"1","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"],"recovered":True},{"episode_id":"2","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o2"],"recovered":True}]
        self.assertEqual(analyze_repeated_agent_episodes(eps)[0].pattern_type, "RECOVERY_PATTERN")

    def test_echo_pattern_is_detected_without_independent_origins(self):
        eps = [{"episode_id":"1","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"],"echo":True},{"episode_id":"2","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"],"echo":True}]
        p = analyze_repeated_agent_episodes(eps)[0]
        self.assertEqual(p.pattern_type, "ECHO_PATTERN")
        self.assertEqual(p.effective_independent_origins, 1)


if __name__ == "__main__":
    unittest.main()

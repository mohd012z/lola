import unittest
from lola_episode_orchestrator import engines_for_event

class EpisodeOrchestratorTests(unittest.TestCase):
    def test_handoff_routes_task_and_agent(self): self.assertEqual(engines_for_event("agent.handoff"),("TASK","AGENT"))
    def test_failure_routes_failure_projection(self): self.assertEqual(engines_for_event("agent.failure"),("TASK","AGENT","FAILURE"))
    def test_verification_routes_learning(self): self.assertEqual(engines_for_event("cognitive.verification"),("TASK","AGENT","LEARNING"))
    def test_unknown_event_is_task_only(self): self.assertEqual(engines_for_event("unknown"),("TASK",))

if __name__ == "__main__": unittest.main()

import unittest
from lola_adaptive_cycle_orchestrator import orchestrate_adaptive_cycle

class AdaptiveCycleOrchestratorTests(unittest.TestCase):
    def test_changed_memory_traces_refresh_replay_and_recheck(self):
        records=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":"old"},{"knowledge_id":"k1","version":2,"state":"ACTIVE","supersedes_version":1,"payload":"new"}]
        r=orchestrate_adaptive_cycle(records=records,snapshot={"k1":1},dependencies={"h1":["k1"],"h2":["k2"]},before={"h1":"A","h2":"B"},after={"h1":"C","h2":"B"},contradictions=0,unknowns=0,trace_id="t1")
        self.assertEqual(r.status,"RECHECK")
        self.assertEqual(r.replay_hypothesis_ids,("h1",))
        self.assertEqual(r.trace_id,"t1")
        self.assertFalse(r.execution_authority)

    def test_quarantined_memory_blocks_before_replay(self):
        records=[{"knowledge_id":"k1","version":1,"state":"ACTIVE"},{"knowledge_id":"k1","version":2,"state":"QUARANTINED","supersedes_version":1}]
        r=orchestrate_adaptive_cycle(records=records,snapshot={"k1":1},dependencies={"h1":["k1"]},before={"h1":"A"},after={},contradictions=0,unknowns=0,trace_id="t2")
        self.assertEqual(r.status,"BLOCKED")
        self.assertEqual(r.replay_hypothesis_ids,())

if __name__ == "__main__": unittest.main()

import unittest
from lola_traced_adaptive_cycle import run_traced_adaptive_cycle

class TracedAdaptiveCycleTests(unittest.TestCase):
    def test_cycle_emits_verified_stage_trace(self):
        records=[{"knowledge_id":"k1","version":1,"state":"ACTIVE","payload":"old"},{"knowledge_id":"k1","version":2,"state":"ACTIVE","supersedes_version":1,"payload":"new"}]
        r=run_traced_adaptive_cycle(records=records,snapshot={"k1":1},dependencies={"h1":["k1"]},before={"h1":"A"},after={"h1":"C"},contradictions=0,unknowns=0,trace_id="t1")
        self.assertEqual(r.cycle.status,"RECHECK")
        self.assertEqual(r.verification.status,"VERIFIED")
        self.assertEqual(tuple(e.stage for e in r.entries),("MEMORY_REFRESH","DEPENDENCY_REPLAY","REASONING_DELTA","FEEDBACK"))
        self.assertFalse(r.execution_authority)

    def test_blocked_refresh_has_short_trace(self):
        records=[{"knowledge_id":"k1","version":1,"state":"ACTIVE"},{"knowledge_id":"k1","version":2,"state":"QUARANTINED","supersedes_version":1}]
        r=run_traced_adaptive_cycle(records=records,snapshot={"k1":1},dependencies={"h1":["k1"]},before={"h1":"A"},after={},contradictions=0,unknowns=0,trace_id="t2")
        self.assertEqual(r.cycle.status,"BLOCKED")
        self.assertEqual(tuple(e.stage for e in r.entries),("MEMORY_REFRESH",))
        self.assertEqual(r.verification.status,"VERIFIED")

if __name__ == "__main__": unittest.main()

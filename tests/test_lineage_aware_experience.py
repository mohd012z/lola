import unittest
from lola_lineage_experience import compile_lineage_experience

class LineageAwareExperienceTests(unittest.TestCase):
    def test_shared_ancestry_is_one_effective_origin(self):
        nodes=[{"evidence_id":"root","origin_domain":"artifact:x","parent_ids":[]},{"evidence_id":"a","origin_domain":"agent:a","parent_ids":["root"]},{"evidence_id":"b","origin_domain":"agent:b","parent_ids":["root"]}]
        episodes=[{"episode_id":"1","evidence_ids":["a"],"outcome":"VERIFIED"},{"episode_id":"2","evidence_ids":["b"],"outcome":"VERIFIED"}]
        out=compile_lineage_experience(nodes,episodes)
        self.assertEqual(out.independent_root_ids,("root",))
        self.assertEqual(out.effective_independent_origins,1)

    def test_distinct_ancestry_survives(self):
        nodes=[{"evidence_id":"a","origin_domain":"artifact:a","parent_ids":[]},{"evidence_id":"b","origin_domain":"runtime:b","parent_ids":[]}]
        episodes=[{"episode_id":"1","evidence_ids":["a"],"outcome":"VERIFIED"},{"episode_id":"2","evidence_ids":["b"],"outcome":"VERIFIED"}]
        out=compile_lineage_experience(nodes,episodes)
        self.assertEqual(out.effective_independent_origins,2)

    def test_failed_episode_is_counterexample(self):
        nodes=[{"evidence_id":"a","origin_domain":"a","parent_ids":[]},{"evidence_id":"b","origin_domain":"b","parent_ids":[]}]
        episodes=[{"episode_id":"ok","evidence_ids":["a"],"outcome":"VERIFIED"},{"episode_id":"bad","evidence_ids":["b"],"outcome":"FAILED"}]
        self.assertEqual(compile_lineage_experience(nodes,episodes).counterexample_episode_ids,("bad",))

if __name__ == "__main__": unittest.main()

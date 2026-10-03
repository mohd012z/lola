import unittest
from lola_ax_experience import aggregate_ax

class AXExperienceTests(unittest.TestCase):
    def test_context_and_agent_are_preserved(self):
        rows=aggregate_ax([
            {"episode_id":"1","agent_id":"A","domain":"build","problem_class":"compile","outcome":"VERIFIED","origin_roots":["o1"],"information_gain":1.0},
            {"episode_id":"2","agent_id":"B","domain":"build","problem_class":"compile","outcome":"FAILED","origin_roots":["o2"],"information_gain":0.2},
        ])
        self.assertEqual(len(rows),2)
        self.assertEqual({r.agent_id for r in rows},{"A","B"})

    def test_shared_origin_is_not_double_counted_inside_context(self):
        row=aggregate_ax([
            {"episode_id":"1","agent_id":"A","domain":"build","problem_class":"compile","outcome":"VERIFIED","origin_roots":["same"]},
            {"episode_id":"2","agent_id":"A","domain":"build","problem_class":"compile","outcome":"VERIFIED","origin_roots":["same"]},
        ])[0]
        self.assertEqual(row.episode_count,2)
        self.assertEqual(row.independent_origin_count,1)

if __name__ == "__main__": unittest.main()

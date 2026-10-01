import unittest
from lola_experience_compiler import compile_experience


class ExperienceCompilerTests(unittest.TestCase):
    def test_duplicate_episode_ids_are_collapsed(self):
        eps=[{"episode_id":"e1","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"]},{"episode_id":"e1","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"]}]
        out=compile_experience(eps)
        self.assertEqual(out.input_episode_count,2)
        self.assertEqual(out.unique_episode_count,1)

    def test_shared_origins_are_collapsed(self):
        eps=[{"episode_id":"e1","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"]},{"episode_id":"e2","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"]}]
        out=compile_experience(eps)
        self.assertEqual(out.effective_independent_origins,1)

    def test_counterexamples_are_retained(self):
        eps=[{"episode_id":"ok","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"]},{"episode_id":"bad","context":{"domain":"x"},"outcome":"FAILED","origin_domains":["o2"]}]
        out=compile_experience(eps)
        self.assertEqual(out.counterexample_episode_ids,("bad",))
        self.assertEqual(out.patterns[0].pattern_type,"CONDITIONAL_PATTERN")

    def test_output_is_deterministic(self):
        eps=[{"episode_id":"b","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o2"]},{"episode_id":"a","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"]}]
        self.assertEqual(compile_experience(eps),compile_experience(reversed(eps)))

    def test_compiler_does_not_promote_memory(self):
        out=compile_experience([{"episode_id":"a","context":{"domain":"x"},"outcome":"VERIFIED","origin_domains":["o1"]}])
        self.assertEqual(out.status,"ANALYZED")
        self.assertFalse(hasattr(out,"verified_memory"))


if __name__ == "__main__": unittest.main()

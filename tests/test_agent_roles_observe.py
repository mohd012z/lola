import unittest

from lola_agent_roles import (
    COGNITIVE_ROLES, LIFECYCLE, derive_roles, role_for_question_type,
)
from lola_observe import (
    Observation, compute_prediction_error, predict, record_observation,
)


class RoleDerivationTests(unittest.TestCase):
    def test_roles_is_the_seven_set(self):
        self.assertEqual(
            set(COGNITIVE_ROLES),
            {"EXPLORER", "ANALYST", "SKEPTIC", "RESEARCHER",
             "EXPERIMENTER", "VERIFIER", "SYNTHESIZER"},
        )

    def test_lifecycle_order(self):
        self.assertEqual(LIFECYCLE, (
            "EXPLORER", "ANALYST", "RESEARCHER", "SKEPTIC",
            "EXPERIMENTER", "VERIFIER", "SYNTHESIZER",
        ))

    def test_troubleshooting_derives_exploration_and_verification(self):
        roles = derive_roles("why does the build fail", gap=("lifecycle",))
        # a failure question needs exploration + mechanism + skepticism
        # + experimentation + verification; it is not research-first.
        self.assertIn("EXPLORER", roles)
        self.assertIn("ANALYST", roles)
        self.assertIn("SKEPTIC", roles)
        self.assertIn("EXPERIMENTER", roles)
        self.assertIn("VERIFIER", roles)

    def test_research_question_includes_researcher(self):
        roles = derive_roles("research the evidence for scheduling options",
                             gap=("prior_art",))
        self.assertIn("RESEARCHER", roles)
        self.assertIn("SYNTHESIZER", roles)

    def test_implementation_includes_experimenter_and_verifier(self):
        roles = derive_roles("implement the new pipeline", gap=("change",))
        self.assertIn("EXPERIMENTER", roles)
        self.assertIn("VERIFIER", roles)

    def test_minimal_not_maximal(self):
        # SYNTHESIZER only appears when there is more than one stream to
        # integrate (a gap present). A single known fact needs no synthesis.
        roles_single = derive_roles("what is the decoder buffer size",
                                    gap=())
        roles_multi = derive_roles("why does it fail", gap=("a", "b"))
        self.assertNotIn("SYNTHESIZER", roles_single)
        self.assertIn("SYNTHESIZER", roles_multi)

    def test_deterministic_and_sorted_by_lifecycle(self):
        a = derive_roles("why does it fail", gap=("x",))
        b = derive_roles("why does it fail", gap=("x",))
        self.assertEqual(a, b)
        # returned in LIFECYCLE order
        idx = {r: i for i, r in enumerate(LIFECYCLE)}
        self.assertEqual(a, tuple(sorted(a, key=lambda r: idx[r])))

    def test_question_type_role_map(self):
        self.assertIn("RESEARCHER", role_for_question_type("RESEARCH"))
        self.assertIn("EXPERIMENTER", role_for_question_type("IMPLEMENTATION"))
        self.assertIn("SKEPTIC", role_for_question_type("TROUBLESHOOTING"))
        # every type must still end in VERIFIER + SYNTHESIZER
        for t in ("TROUBLESHOOTING", "RESEARCH", "IMPLEMENTATION", "GENERIC"):
            roles = role_for_question_type(t)
            self.assertIn("VERIFIER", roles)
            self.assertIn("SYNTHESIZER", roles)


class PredictionErrorTests(unittest.TestCase):
    def test_exact_prediction_zero_error(self):
        err = compute_prediction_error(predict(10), 10)
        self.assertAlmostEqual(err, 0.0)

    def test_error_is_signed_delta_observed_minus_expected(self):
        err = compute_prediction_error(predict(5), 8)
        self.assertAlmostEqual(err, 3.0)

    def test_record_observation_stores_delta(self):
        obs = record_observation("e1", expected=5, observed=8,
                                 source="test_run")
        self.assertAlmostEqual(obs.prediction_error, 3.0)
        self.assertEqual(obs.source, "test_run")

    def test_observation_is_immutable(self):
        obs = record_observation("e1", expected=1, observed=2)
        with self.assertRaises(AttributeError):
            obs.observed = 99

    def test_prediction_error_drives_recheck(self):
        # non-zero error -> the loop must RECHECK (re-observe), not answer
        obs = record_observation("e1", expected=5, observed=8)
        self.assertTrue(obs.needs_recheck)
        clean = record_observation("e2", expected=5, observed=5)
        self.assertFalse(clean.needs_recheck)


class LoopObserveIntegrationTests(unittest.TestCase):
    def test_report_carries_prediction_error_when_observed(self):
        from lola_runtime_loop import run_loop
        # a question we can observe; prediction off by one
        r = run_loop(
            "what is the decoder buffer size",
            verified_state={"decoder buffer size": "8192 bytes"},
            inspectable=(),
            prediction=8193,
            observed=8192,
        )
        self.assertTrue(hasattr(r, "prediction_error"))
        self.assertAlmostEqual(r.prediction_error, -1.0)  # observed - expected
        self.assertTrue(hasattr(r, "needs_recheck"))
        self.assertFalse(r.needs_recheck)

    def test_no_observation_is_none(self):
        from lola_runtime_loop import run_loop
        r = run_loop("what is the decoder buffer size",
                     verified_state={"decoder buffer size": "8192 bytes"})
        self.assertIsNone(r.prediction_error)
        self.assertFalse(r.needs_recheck)

    def test_large_error_flags_recheck(self):
        from lola_runtime_loop import run_loop
        r = run_loop("what is the decoder buffer size",
                     verified_state={"decoder buffer size": "8192 bytes"},
                     prediction=100, observed=8192)
        self.assertTrue(r.needs_recheck)


if __name__ == "__main__":
    unittest.main()

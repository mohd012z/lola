import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from lola import main
from lola_sovereign_runtime import (
    CapabilityEnvelope,
    CognitiveState,
    apply_observation,
    next_best_action,
    run_sovereign_smoke,
    select_capability,
)


class SovereignRuntimeTests(unittest.TestCase):
    def test_local_capability_is_preferred_over_remote(self):
        envelope = CapabilityEnvelope(
            local=("local_reasoner", "in_ai"),
            remote=("frontier_reasoner",),
            network_available=True,
        )
        selected = select_capability(
            envelope,
            local_candidates=("local_reasoner",),
            remote_candidates=("frontier_reasoner",),
        )
        self.assertEqual(selected, "local_reasoner")

    def test_remote_capability_is_unavailable_during_blackout(self):
        envelope = CapabilityEnvelope(
            local=("in_ai",),
            remote=("frontier_reasoner",),
            network_available=False,
        )
        selected = select_capability(
            envelope,
            local_candidates=("local_reasoner",),
            remote_candidates=("frontier_reasoner",),
        )
        self.assertIsNone(selected)

    def test_gap_routes_to_smallest_decisive_action(self):
        state = CognitiveState(
            objective="find root cause",
            unknowns=("cause",),
            gap_type="OBSERVATION",
        )
        action = next_best_action(state)
        self.assertEqual(action.kind, "OBSERVE")
        self.assertFalse(action.execution_authority)

    def test_observation_builds_transaction_and_verifies_resolution(self):
        before = CognitiveState(
            objective="find root cause",
            status="BLOCKED",
            unknowns=("cause",),
            gap_type="OBSERVATION",
        )
        after = CognitiveState(
            objective="find root cause",
            status="READY",
            unknowns=(),
            gap_type="NONE",
            verified=True,
        )
        step = apply_observation(
            transaction_id="tx1",
            state_before=before,
            action="inspect dependency",
            expected_delta={"unknowns_removed": ("cause",)},
            state_after=after,
            evidence_ids=("e1", "e1"),
        )
        self.assertEqual(step.resolution, "VERIFIED_SOLVED")
        self.assertFalse(step.transaction.prediction_error)
        self.assertEqual(step.transaction.evidence_ids, ("e1",))
        self.assertFalse(step.transaction.verification_authority)

    def test_prediction_error_rejects_false_solved_state(self):
        before = CognitiveState(
            objective="find root cause",
            status="BLOCKED",
            unknowns=("cause",),
            gap_type="OBSERVATION",
        )
        after = CognitiveState(
            objective="find root cause",
            status="BLOCKED",
            unknowns=("cause",),
            gap_type="OBSERVATION",
            verified=True,
        )
        step = apply_observation(
            transaction_id="tx2",
            state_before=before,
            action="inspect dependency",
            expected_delta={"unknowns_removed": ("cause",)},
            state_after=after,
            evidence_ids=("e2",),
        )
        self.assertTrue(step.transaction.prediction_error)
        self.assertEqual(step.resolution, "REFOCUS")

    def test_sovereign_smoke_runs_without_external_capability(self):
        result = run_sovereign_smoke()
        self.assertTrue(result["passed"])
        self.assertEqual(result["mode"], "S0-SOVEREIGN")
        self.assertFalse(result["external_used"])
        self.assertEqual(result["resolution"], "VERIFIED_SOLVED")

    def test_cli_cognitive_smoke_runs_without_target(self):
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["lola.py", "--cognitive-smoke"]):
            with redirect_stdout(stdout):
                rc = main()
        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["mode"], "S0-SOVEREIGN")


if __name__ == "__main__":
    unittest.main()

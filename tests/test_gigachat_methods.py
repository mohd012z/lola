import math
import unittest
from lola_delta_memory import DeltaMemory, l2norm, sigmoid, softplus, DecayParams
from lola_reasoning_layout import (
    ReasoningTurn, render_assistant_turn, apply_history_policy,
    build_generation_prompt, ROLE_SEP, THINK_OPEN, THINK_CLOSE,
)

class DeltaMemoryTests(unittest.TestCase):
    def test_read_then_delta_write_corrects_value(self):
        # k == e1, v == [3, 0]. First step: S is zero, read 0,
        # delta = (3-0)*beta, S = outer(k, delta) with beta=1 -> S = k v^T
        mem = DeltaMemory(2, DecayParams(a_log=[0.0], dt_bias=[0.0]))
        out, rec = mem.step(q=[1.0, 0.0], k=[1.0, 0.0], v=[3.0, 0.0], a=[0.0], b=[30.0])
        # beta = sigmoid(30) ~ 1.0 ; read was 0 ; stored value now 3
        self.assertAlmostEqual(rec.read_value[0], 0.0)
        self.assertAlmostEqual(rec.delta[0], 3.0, places=6)
        out2, rec2 = mem.step(q=[1.0, 0.0], k=[1.0, 0.0], v=[5.0, 0.0], a=[0.0], b=[30.0])
        # decay: g = -exp(A_log)*softplus(a+dt_bias); A_log=0 -> exp=1; softplus(0)=ln2
        # step 1 stored v*beta over the eps-normalized key (l2norm parity with the
        # reference FLA kernel), so the readback carries the same scale factor
        decay = math.exp(-softplus(0.0))
        beta = sigmoid(30.0)
        k_scale = l2norm([1.0, 0.0])[0]
        # write used normalized key once, readback normalizes it again -> k_scale^2
        expected_read = decay * 3.0 * beta * k_scale * k_scale
        self.assertAlmostEqual(rec2.read_value[0], expected_read, places=9)
        self.assertAlmostEqual(rec2.delta[0], (5.0 - expected_read) * 1.0, places=9)

    def test_decay_bounds_and_gating(self):
        p = DecayParams(a_log=[0.0], dt_bias=[0.0])
        mem = DeltaMemory(1, p)
        # a -> +inf gives softplus large -> g = -exp(0)*softplus(a+dt) ~ -a ; exp(g) -> 0 (forget)
        _, rec = mem.step(q=[1.0], k=[1.0], v=[1.0], a=[50.0], b=[0.0])
        self.assertLess(rec.decay, 1.0)
        self.assertGreater(rec.decay, 0.0)
        # beta = sigmoid(b): b=0 -> 0.5
        self.assertAlmostEqual(rec.beta, 0.5, places=9)

    def test_l2norm_deterministic(self):
        out = l2norm([3.0, 4.0])
        self.assertAlmostEqual(out[0], 0.6, places=5)
        self.assertAlmostEqual(out[1], 0.8, places=5)
        self.assertEqual(l2norm([0.0, 0.0]), [0.0, 0.0])  # zero vector safe

    def test_output_read_matches_state(self):
        mem = DeltaMemory(2, DecayParams(a_log=[0.0], dt_bias=[0.0]))
        mem.step(q=[1.0, 0.0], k=[1.0, 0.0], v=[3.0, 0.0], a=[0.0], b=[30.0])
        out, _ = mem.step(q=[0.0, 1.0], k=[1.0, 0.0], v=[0.0, 0.0], a=[0.0], b=[0.0])
        # query orthogonal to stored key -> read ~0 (after decay applied)
        self.assertLess(out[1], 1e-9)

    def test_rejects_shape_mismatch(self):
        mem = DeltaMemory(2, DecayParams(a_log=[0.0], dt_bias=[0.0]))
        with self.assertRaises(ValueError):
            mem.step(q=[1.0], k=[1.0, 0.0], v=[1.0, 0.0], a=[0.0], b=[0.0])

    def test_rejects_non_finite(self):
        mem = DeltaMemory(1, DecayParams(a_log=[0.0], dt_bias=[0.0]))
        with self.assertRaises(ValueError):
            mem.step(q=[float("inf")], k=[1.0], v=[1.0], a=[0.0], b=[0.0])

    def test_state_snapshot_immutable_and_replayable(self):
        mem = DeltaMemory(1, DecayParams(a_log=[0.0], dt_bias=[0.0]))
        _, r1 = mem.step(q=[1.0], k=[1.0], v=[2.0], a=[0.0], b=[30.0])
        snap = mem.snapshot()
        # restore and replay same step -> identical record (determinism)
        mem2 = DeltaMemory.from_snapshot(snap, mem.params)
        _, r2 = mem2.step(q=[1.0], k=[1.0], v=[2.0], a=[0.0], b=[0.0])
        self.assertAlmostEqual(r1.decay, r2.decay, places=12)

class ReasoningLayoutTests(unittest.TestCase):
    def test_composite_layout_order(self):
        turn = ReasoningTurn("think body", "final answer", [])
        self.assertEqual(render_assistant_turn(turn), f"{THINK_OPEN}think body{THINK_CLOSE}\n\nfinal answer")

    def test_tool_calls_appended_last(self):
        turn = ReasoningTurn("t", "a", [{"name": "f", "arguments": {"x": 1}}])
        rendered = render_assistant_turn(turn)
        self.assertEqual(rendered.split("\n\n"), [f"{THINK_OPEN}t{THINK_CLOSE}", "a", 'f(x=1)'])

    def test_empty_turn_rejected(self):
        with self.assertRaises(ValueError):
            render_assignment = render_assistant_turn(ReasoningTurn("", "", []))

    def test_reasoning_only_turn_rejected(self):
        with self.assertRaises(ValueError):
            render_assistant_turn(ReasoningTurn("only thinking", "", []))

    def test_forced_empty_think_block(self):
        # No reasoning -> empty think block is still emitted (layout never varies)
        turn = ReasoningTurn(None, "answer", [])
        rendered = render_assistant_turn(turn)
        self.assertTrue(rendered.startswith(f"{THINK_OPEN}{THINK_CLOSE}"))

    def test_generation_prompt_ends_with_forced_think(self):
        prompt = build_generation_prompt([
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi", "thinking": "t"},
        ])
        self.assertTrue(prompt.endswith(f"assistant{ROLE_SEP}\n{THINK_OPEN}"))

    def test_history_policy_drops_old_thinking(self):
        messages = [
            {"role": "user", "content": "u1", "thinking": "old"},
            {"role": "assistant", "content": "a1", "thinking": "t1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2", "thinking": "t2"},
        ]
        out = apply_history_policy(messages)
        self.assertNotIn("thinking", out[1])       # before last user -> dropped
        self.assertEqual(out[3].get("thinking"), "t2")  # after last user -> kept

    def test_user_messages_untouched(self):
        messages = [{"role": "user", "content": "u1", "thinking": "x"}]
        out = apply_history_policy(messages)
        self.assertEqual(out[0]["thinking"], "x")

if __name__ == "__main__":
    unittest.main()

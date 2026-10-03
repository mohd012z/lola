import unittest
from lola_cognitive_fabric import KIPEnvelope
from lola_interaction_gateway import (
    TRANSPORTS, TrustClass, ActorIdentity, SessionTable,
    normalize_user_input, interaction_gate, llm_source_envelope,
    grade_llm_output, RoutedCommand,
)
from lola_sovereign_runtime import CapabilityEnvelope, select_capability
from lola_epistemic_fuse import epistemic_fuse

PROV_KEYS = {"actor_id", "session_id", "transport", "trust_class", "authority"}

def _local_actor(*, scopes=()):
    return ActorIdentity("alice", TrustClass.LOCAL_DEVICE, frozenset(scopes))

class NormalizeTests(unittest.TestCase):
    def test_provenance_contract_is_exactly_five_keys(self):
        env = normalize_user_input("cli", "scan /tmp/x", _local_actor(), session_id="s1", kind="command", capability="scan")
        self.assertIsInstance(env, KIPEnvelope)
        self.assertEqual(set(env.provenance.keys()), PROV_KEYS)
        self.assertEqual(env.source, "cli:alice")
        self.assertTrue(env.direct)  # LOCAL_DEVICE is direct
        self.assertEqual(env.kind, "command")
        self.assertEqual(env.provenance["trust_class"], "LOCAL_DEVICE")
        self.assertEqual(env.provenance["authority"], "ADVISORY")

    def test_token_bound_is_not_direct(self):
        actor = ActorIdentity("tg:42", TrustClass.TOKEN_BOUND, frozenset())
        env = normalize_user_input("telegram", "hi", actor, session_id="s2", kind="query", capability="chat")
        self.assertFalse(env.direct)
        self.assertEqual(env.source, "telegram:tg:42")

    def test_execution_scope_carried_in_payload(self):
        env = normalize_user_input("android", "run apk job", _local_actor(scopes=("apk:analyze",)), session_id="s3", kind="command", capability="apk:analyze", requires_execution=True, execution_scope="apk:analyze")
        self.assertTrue(env.payload["requires_execution"])
        self.assertEqual(env.payload["execution_scope"], "apk:analyze")
        self.assertEqual(env.provenance["authority"], "EXECUTE:apk:analyze")

    def test_rejects_unknown_transport(self):
        with self.assertRaises(ValueError):
            normalize_user_input("modem", "x", _local_actor(), session_id="s", kind="query", capability="chat")

    def test_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            normalize_user_input("cli", "   ", _local_actor(), session_id="s", kind="query", capability="chat")

    def test_rejects_bad_kind(self):
        with self.assertRaises(ValueError):
            normalize_user_input("cli", "x", _local_actor(), session_id="s", kind="shout", capability="chat")

    def test_rejects_execution_without_scope(self):
        with self.assertRaises(ValueError):
            normalize_user_input("cli", "x", _local_actor(), session_id="s", kind="command", capability="c", requires_execution=True)

class SessionTableTests(unittest.TestCase):
    def test_session_ids_are_deterministic_and_ordered(self):
        t = SessionTable()
        s1 = t.open_session("alice", "cli")
        s2 = t.open_session("alice", "cli")
        s3 = t.open_session("bob", "cli")
        self.assertNotEqual(s1, s2)
        self.assertNotIn("alice", s3)  # other actor
        # determinism: a fresh table derives the same first session id
        fresh = SessionTable().open_session("alice", "cli")[:24]
        self.assertEqual(s1[:24], fresh)
        self.assertIsNotNone(t.get_session(s1, "cli"))
        self.assertIsNone(t.get_session("nope", "cli"))

class GateTests(unittest.TestCase):
    def _env(self, actor, *, capability="scan", requires_execution=False, scope=None):
        return normalize_user_input("cli", "do " + capability, actor, session_id="s1", kind="command" if requires_execution else "query", capability=capability, requires_execution=requires_execution, execution_scope=scope)

    def test_advisory_query_routes_fast_and_denies_nothing(self):
        env = self._env(_local_actor())
        reg = CapabilityEnvelope(local=("scan",), remote=(), network_available=False)
        out = interaction_gate(env, actors={"alice": _local_actor()}, availability=reg)
        self.assertEqual(out.denied_reasons, ())
        self.assertEqual(out.path, "FAST")
        self.assertFalse(out.execution_authority)
        self.assertIsNone(out.escalation)

    def test_execution_command_routes_cognitive_with_authority(self):
        actor = _local_actor(scopes=("apk:analyze",))
        env = self._env(actor, capability="apk:analyze", requires_execution=True, scope="apk:analyze")
        reg = CapabilityEnvelope(local=("apk:analyze",), remote=(), network_available=False)
        out = interaction_gate(env, actors={"alice": actor}, availability=reg)
        self.assertEqual(out.path, "COGNITIVE")
        self.assertTrue(out.execution_authority)
        self.assertEqual(out.denied_reasons, ())

    def test_unknown_actor_denied_with_escalation(self):
        env = self._env(_local_actor())
        out = interaction_gate(env, actors={}, availability=CapabilityEnvelope())
        self.assertEqual(out.denied_reasons, ("UNKNOWN_ACTOR",))
        self.assertFalse(out.execution_authority)
        self.assertEqual(out.escalation, ("s1", "cli", "UNKNOWN_ACTOR"))

    def test_trust_class_mismatch_denied(self):
        # envelope says LOCAL_DEVICE but the actor table has TOKEN_BOUND for alice
        env = self._env(_local_actor())
        table_actor = ActorIdentity("alice", TrustClass.TOKEN_BOUND, frozenset())
        out = interaction_gate(env, actors={"alice": table_actor}, availability=CapabilityEnvelope())
        self.assertEqual(out.denied_reasons, ("TRUST_MISMATCH",))

    def test_untrusted_actor_never_gets_execution(self):
        actor = ActorIdentity("anon", TrustClass.UNTRUSTED, frozenset({"apk:analyze"}))
        env = normalize_user_input("cli", "run", actor, session_id="s9", kind="command", capability="apk:analyze", requires_execution=True, execution_scope="apk:analyze")
        reg = CapabilityEnvelope(local=("apk:analyze",), remote=(), network_available=False)
        out = interaction_gate(env, actors={"anon": actor}, availability=reg)
        self.assertIn("AUTHORITY_DENIED", out.denied_reasons)
        self.assertFalse(out.execution_authority)

    def test_capability_unavailable_denied(self):
        env = self._env(_local_actor())
        out = interaction_gate(env, actors={"alice": _local_actor()}, availability=CapabilityEnvelope())
        self.assertEqual(out.denied_reasons, ("CAPABILITY_UNAVAILABLE",))

    def test_remote_capability_needs_network(self):
        env = self._env(_local_actor(), capability="frontier_reasoner")
        reg_off = CapabilityEnvelope(local=(), remote=("frontier_reasoner",), network_available=False)
        reg_on = CapabilityEnvelope(local=(), remote=("frontier_reasoner",), network_available=True)
        denied = interaction_gate(env, actors={"alice": _local_actor()}, availability=reg_off)
        ok = interaction_gate(env, actors={"alice": _local_actor()}, availability=reg_on)
        self.assertEqual(denied.denied_reasons, ("CAPABILITY_UNAVAILABLE",))
        self.assertEqual(ok.denied_reasons, ())

    def test_scope_mismatch_denied(self):
        actor = _local_actor(scopes=("apk:analyze",))
        env = self._env(actor, capability="apk:analyze", requires_execution=True, scope="apk:delete")
        reg = CapabilityEnvelope(local=("apk:analyze",), remote=(), network_available=False)
        out = interaction_gate(env, actors={"alice": actor}, availability=reg)
        self.assertEqual(out.denied_reasons, ("AUTHORITY_DENIED",))

class LlmSourceFabricTests(unittest.TestCase):
    def test_tiers_map_to_local_and_remote(self):
        env = llm_source_envelope({"tiny_local", "large_local", "remote_optional"}, network_available=True)
        self.assertEqual(env.local, ("tiny_local", "large_local"))
        self.assertEqual(env.remote, ("remote_optional",))

    def test_sovereign_path_reachable_without_models(self):
        env = llm_source_envelope(set(), network_available=False)
        self.assertEqual(env.local, ())
        self.assertEqual(env.remote, ())
        # S0: nothing selected, no crash
        self.assertIsNone(select_capability(env, local_candidates=("tiny_local",), remote_candidates=("remote_optional",)))

    def test_remote_never_selected_when_network_down(self):
        env = llm_source_envelope({"tiny_local", "remote_optional"}, network_available=False)
        self.assertEqual(
            select_capability(env, local_candidates=("tiny_local",), remote_candidates=("remote_optional",)),
            "tiny_local",
        )
        # with only remote available and no network -> sovereign fallback, not remote
        env2 = llm_source_envelope({"remote_optional"}, network_available=False)
        self.assertIsNone(select_capability(env2, local_candidates=(), remote_candidates=("remote_optional",)))

    def test_unknown_tier_rejected(self):
        with self.assertRaises(ValueError):
            llm_source_envelope({"giga_local"}, network_available=True)

    def test_llm_output_grade_capped_at_inferred(self):
        for tier in ("tiny_local", "large_local", "remote_optional"):
            self.assertEqual(grade_llm_output(tier), "E3_INFERRED")
        with self.assertRaises(ValueError):
            grade_llm_output("user_claim")

class FuseTests(unittest.TestCase):
    def test_unverified_passes_through(self):
        out = epistemic_fuse(verified=False, evidence_ids=(), observation_evidence_ids=(), contradictions=())
        self.assertEqual(out.result, "PASS")
        self.assertEqual(out.reason, "NOT_VERIFIED")

    def test_contradiction_always_cuts(self):
        out = epistemic_fuse(verified=True, evidence_ids=("obs1",), observation_evidence_ids=("obs1",), contradictions=("c1",))
        self.assertEqual((out.result, out.reason), ("CUT", "CONTRADICTION"))

    def test_verified_without_any_evidence_cuts(self):
        out = epistemic_fuse(verified=True, evidence_ids=(), observation_evidence_ids=(), contradictions=())
        self.assertEqual((out.result, out.reason), ("CUT", "NO_EVIDENCE"))

    def test_user_claim_only_cuts(self):
        # claim cites evidence, but none of it is observation-grade
        out = epistemic_fuse(verified=True, evidence_ids=("user1", "model2"), observation_evidence_ids=(), contradictions=())
        self.assertEqual((out.result, out.reason), ("CUT", "USER_CLAIM_ONLY"))

    def test_observed_evidence_passes(self):
        out = epistemic_fuse(verified=True, evidence_ids=("user1", "obs1"), observation_evidence_ids=("obs1",), contradictions=())
        self.assertEqual((out.result, out.reason), ("PASS", "OBSERVED"))

    def test_cited_observation_not_in_evidence_cuts(self):
        # observation id claimed but not actually cited by the verified claim
        out = epistemic_fuse(verified=True, evidence_ids=("user1",), observation_evidence_ids=("obs1",), contradictions=())
        self.assertEqual(out.result, "CUT")

if __name__ == "__main__":
    unittest.main()

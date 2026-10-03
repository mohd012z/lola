import unittest

from lola_cognitive_entry import cognitive_entry
from lola_interaction_gateway import (
    ActorIdentity, CapabilityEnvelope, TrustClass, llm_source_envelope,
)


def _actor(
    actor_id="fatah",
    trust_class=TrustClass.LOCAL_DEVICE,
    scopes=("cognitive_query",),
):
    return ActorIdentity(
        actor_id=actor_id,
        trust_class=trust_class,
        granted_scopes=frozenset(scopes),
    )


def _s0(capability="cognitive_query"):
    return CapabilityEnvelope(local=(capability,), remote=(),
                              network_available=False)


class DenialBeforeCognitionTests(unittest.TestCase):
    def test_unknown_actor_denied_no_report(self):
        out = cognitive_entry(
            "cli", "what is the decoder buffer size", _actor(),
            session_id="sess-1", actors={}, availability=_s0(),
        )
        self.assertEqual(out.status, "DENIED")
        self.assertEqual(out.gate["denied_reasons"], ("UNKNOWN_ACTOR",))
        self.assertIsNone(out.report)
        self.assertIsNotNone(out.escalation)

    def test_trust_mismatch_denied(self):
        actor = _actor()
        out = cognitive_entry(
            "cli", "q", actor, session_id="sess-1",
            actors={"fatah": _actor(trust_class=TrustClass.TOKEN_BOUND)},
            availability=_s0(),
        )
        self.assertEqual(out.gate["denied_reasons"], ("TRUST_MISMATCH",))
        self.assertIsNone(out.report)

    def test_untrusted_can_never_execute(self):
        out = cognitive_entry(
            "cli", "run the build", _actor(trust_class=TrustClass.UNTRUSTED),
            session_id="sess-1", actors={"fatah": _actor(trust_class=TrustClass.UNTRUSTED)},
            availability=_s0(), requires_execution=True, execution_scope="build",
        )
        self.assertEqual(out.status, "DENIED")
        self.assertIsNone(out.report)

    def test_capability_unavailable_denied(self):
        out = cognitive_entry(
            "cli", "q", _actor(), session_id="sess-1",
            actors={"fatah": _actor()},
            availability=CapabilityEnvelope(local=(), remote=(),
                                            network_available=False),
        )
        self.assertEqual(out.gate["denied_reasons"], ("CAPABILITY_UNAVAILABLE",))
        self.assertIsNone(out.report)

    def test_execution_without_scope_denied(self):
        out = cognitive_entry(
            "cli", "deploy", _actor(), session_id="sess-1",
            actors={"fatah": _actor()}, availability=_s0(),
            requires_execution=True, execution_scope="deploy",
        )
        # actor granted only cognitive_query, not deploy
        self.assertEqual(out.gate["denied_reasons"], ("AUTHORITY_DENIED",))
        self.assertIsNone(out.report)

    def test_escalation_carries_session_transport_reason(self):
        out = cognitive_entry(
            "telegram", "q", _actor(), session_id="sess-xyz",
            actors={}, availability=_s0(),
        )
        self.assertEqual(out.escalation, ("sess-xyz", "telegram", "UNKNOWN_ACTOR"))


class AllowedPathTests(unittest.TestCase):
    def test_query_allowed_runs_loop(self):
        out = cognitive_entry(
            "cli", "what is the decoder buffer size", _actor(),
            session_id="sess-1", actors={"fatah": _actor()},
            availability=_s0(),
            verified_state={"decoder buffer size": "8192 bytes"},
        )
        self.assertEqual(out.status, "ANSWERED")
        self.assertEqual(out.gate["denied_reasons"], ())
        self.assertIsNotNone(out.report)
        self.assertEqual(out.report["route"], "ANSWER")
        self.assertEqual(out.session_id, "sess-1")
        self.assertEqual(out.transport, "cli")

    def test_execution_granted_routes_cognitive(self):
        out = cognitive_entry(
            "android", "implement the change", _actor(scopes=("cognitive_query", "build")),
            session_id="sess-2",
            actors={"fatah": _actor(scopes=("cognitive_query", "build"))},
            availability=_s0(),
            requires_execution=True, execution_scope="build",
        )
        self.assertEqual(out.status, "ANSWERED")
        self.assertTrue(out.gate["execution_authority"])
        self.assertEqual(out.gate["path"], "COGNITIVE")

    def test_default_s0_envelope(self):
        # no availability given -> default S0 lets the query through
        out = cognitive_entry(
            "cli", "why does it fail", _actor(), session_id="sess-1",
            actors={"fatah": _actor()},
        )
        self.assertEqual(out.status, "ANSWERED")


class FuseLaw1Tests(unittest.TestCase):
    def test_clean_research_fuses_observed(self):
        out = cognitive_entry(
            "cli", "why does it freeze", _actor(), session_id="sess-1",
            actors={"fatah": _actor()}, availability=_s0(),
            frozen_idea={"frozen_before_external": True},
            external_hits=("primary source says Y",),
        )
        # SUPPORTED confidence + observation-grade bus evidence -> PASS
        self.assertIsNotNone(out.fuse)
        self.assertEqual(out.fuse["result"], "PASS")

    def test_quarantined_external_fuses_cut(self):
        out = cognitive_entry(
            "cli", "why does it freeze", _actor(), session_id="sess-1",
            actors={"fatah": _actor()}, availability=_s0(),
            frozen_idea={"frozen_before_external": False},
            external_hits=("study says X",),
        )
        # quarantined: a user/external claim without verified observation
        # evidence is CUT — never treated as verification (Law 1)
        self.assertIsNotNone(out.fuse)
        self.assertEqual(out.fuse["result"], "CUT")
        self.assertTrue(out.report["quarantined"])

    def test_no_external_no_fuse(self):
        out = cognitive_entry(
            "cli", "what is the decoder buffer size", _actor(),
            session_id="sess-1", actors={"fatah": _actor()},
            verified_state={"decoder buffer size": "8192 bytes"},
        )
        self.assertIsNone(out.fuse)


class EntryCliTest(unittest.TestCase):
    def test_cli_entry_runs(self):
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        doc = {
            "transport": "cli",
            "raw": "what is the decoder buffer size",
            "actor": {"actor_id": "fatah",
                       "trust_class": "LOCAL_DEVICE",
                       "granted_scopes": ["cognitive_query"]},
            "session_id": "sess-1",
            "verified_state": {"decoder buffer size": "8192 bytes"},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as f:
            json.dump(doc, f)
            path = f.name
        proc = subprocess.run(
            [sys.executable, "lola.py", "--cognitive-entry", path],
            capture_output=True, text=True, cwd=repo_root,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ANSWERED")
        self.assertEqual(payload["report"]["route"], "ANSWER")

    def test_cli_entry_denied_still_reports(self):
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        doc = {
            "transport": "cli",
            "raw": "q",
            "actor": {"actor_id": "stranger",
                       "trust_class": "UNTRUSTED",
                       "granted_scopes": []},
            "session_id": "sess-1",
            "actors": {},  # empty table -> UNKNOWN_ACTOR
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as f:
            json.dump(doc, f)
            path = f.name
        proc = subprocess.run(
            [sys.executable, "lola.py", "--cognitive-entry", path],
            capture_output=True, text=True, cwd=repo_root,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "DENIED")
        self.assertIsNone(payload["report"])
        self.assertEqual(payload["gate"]["denied_reasons"], ["UNKNOWN_ACTOR"])


if __name__ == "__main__":
    unittest.main()

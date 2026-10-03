from dataclasses import replace

from llm_security.evidence_chain import EvidenceChain, GENESIS


def test_empty_chain_is_valid():
    assert EvidenceChain.verify(())


def test_events_are_sha_chained():
    chain = EvidenceChain()
    first = chain.append("SCAN", "a" * 64, {"score": 0.1}, timestamp="2026-01-01T00:00:00+00:00")
    second = chain.append("POLICY", "a" * 64, {"action": "ALLOW"}, timestamp="2026-01-01T00:00:01+00:00")
    assert first.parent_sha256 == GENESIS
    assert second.parent_sha256 == first.event_sha256
    assert chain.head == second.event_sha256
    assert EvidenceChain.verify(chain.events)


def test_payload_tampering_is_detected():
    chain = EvidenceChain()
    event = chain.append("SCAN", "a" * 64, {"score": 0.1}, timestamp="2026-01-01T00:00:00+00:00")
    tampered = replace(event, payload={"score": 0.9})
    assert not EvidenceChain.verify((tampered,))


def test_parent_tampering_is_detected():
    chain = EvidenceChain()
    first = chain.append("SCAN", "a" * 64, {}, timestamp="2026-01-01T00:00:00+00:00")
    second = chain.append("POLICY", "a" * 64, {}, timestamp="2026-01-01T00:00:01+00:00")
    tampered_second = replace(second, parent_sha256="f" * 64)
    assert not EvidenceChain.verify((first, tampered_second))


def test_reordering_is_detected():
    chain = EvidenceChain()
    first = chain.append("SCAN", "a" * 64, {}, timestamp="2026-01-01T00:00:00+00:00")
    second = chain.append("POLICY", "a" * 64, {}, timestamp="2026-01-01T00:00:01+00:00")
    assert not EvidenceChain.verify((second, first))

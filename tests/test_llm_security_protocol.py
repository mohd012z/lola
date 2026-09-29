import pytest

from llm_security.protocol import (
    MAX_OPTIONS_BYTES,
    MAX_SOURCE_BYTES,
    GuardRequest,
    Operation,
    ProtocolError,
    SourceRef,
    WorkerFinding,
    WorkerResult,
)


def test_request_fingerprint_is_stable():
    source = SourceRef(path="sample.py", sha256="a" * 64, size=12)
    request = GuardRequest(
        operation=Operation.SCAN,
        source=source,
        request_id="request-1",
        run_id="run-1",
        options={"references": True},
    )
    request.validate()
    assert request.fingerprint() == request.fingerprint()
    assert len(request.fingerprint()) == 64


def test_worker_result_reports_observation_only():
    finding = WorkerFinding(
        worker="structure",
        kind="structural_anomaly",
        score=0.4,
        locator="sample.py:1",
    )
    result = WorkerResult(
        request_id="request-1",
        run_id="run-1",
        source_sha256="a" * 64,
        worker="structure",
        findings=(finding,),
    )
    result.validate()
    assert result.max_score == 0.4
    assert not hasattr(result, "action")
    assert not hasattr(result, "authorized")


def test_request_rejects_wrong_protocol():
    request = GuardRequest(Operation.SCAN, SourceRef("sample.py", "a" * 64, 1), protocol="GRD/999")
    with pytest.raises(ProtocolError):
        request.validate()


def test_source_rejects_malformed_sha():
    request = GuardRequest(Operation.SCAN, SourceRef("sample.py", "not-a-sha", 1))
    with pytest.raises(ProtocolError):
        request.validate()


def test_source_rejects_oversized_input():
    request = GuardRequest(Operation.SCAN, SourceRef("sample.py", "a" * 64, MAX_SOURCE_BYTES + 1))
    with pytest.raises(ProtocolError):
        request.validate()


def test_options_reject_oversized_payload():
    request = GuardRequest(
        Operation.SCAN,
        SourceRef("sample.py", "a" * 64, 1),
        options={"padding": "x" * (MAX_OPTIONS_BYTES + 1)},
    )
    with pytest.raises(ProtocolError):
        request.validate()


def test_worker_rejects_score_outside_unit_interval():
    result = WorkerResult(
        request_id="request-1",
        run_id="run-1",
        source_sha256="a" * 64,
        worker="structure",
        findings=(WorkerFinding("structure", "bad", 1.5, "sample.py:1"),),
    )
    with pytest.raises(ProtocolError):
        result.validate()

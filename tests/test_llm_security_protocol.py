from llm_security.protocol import GuardRequest, Operation, SourceRef, WorkerFinding, WorkerResult


def test_request_fingerprint_is_stable():
    source = SourceRef(path="sample.py", sha256="a" * 64, size=12)
    request = GuardRequest(
        operation=Operation.SCAN,
        source=source,
        request_id="request-1",
        run_id="run-1",
        options={"references": True},
    )
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
    assert result.max_score == 0.4
    assert not hasattr(result, "action")
    assert not hasattr(result, "authorized")

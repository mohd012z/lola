from llm_security.pipeline import GuardPipeline, SecondaryVerifier
from llm_security.protocol import WorkerFinding, WorkerResult


def worker_result(score: float) -> WorkerResult:
    return WorkerResult(
        request_id="request-1",
        run_id="run-1",
        source_sha256="a" * 64,
        worker="structure",
        findings=(
            WorkerFinding(
                worker="structure",
                kind="structural_anomaly",
                score=score,
                locator="sample.py:1",
            ),
        ),
    )


def test_secondary_is_observation_aggregator():
    score, reasons = SecondaryVerifier().verify([worker_result(0.42)])
    assert score == 0.42
    assert reasons == ("structure:structural_anomaly@sample.py:1",)


def test_secondary_high_risk_can_raise_final_decision():
    decision = GuardPipeline().evaluate("ordinary documentation request", [worker_result(0.9)])
    assert decision.action == "BLOCK"
    assert decision.secondary_score == 0.9

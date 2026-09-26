from lola_evidence import Evidence
from lola_evidence_pipeline import analyze_observations, safe_analyze


def test_pipeline_preserves_provenance_and_counts():
    rows=[Evidence("apk.url","apk-analysis","https://example.test","classes.dex@10","analyze-apk",0.8)]
    result=analyze_observations("demo.apk",rows)
    assert result["status"] == "ok"
    assert result["target"] == "demo.apk"
    assert result["observationCount"] == 1
    assert result["findings"][0]["evidence"][0]["locator"] == "classes.dex@10"


def test_pipeline_keeps_missing_evidence_unknown():
    result=analyze_observations("demo.apk",[],expected_kinds={"apk.url","apk.permission"})
    assert result["missingEvidence"] == ["apk.permission","apk.url"]
    assert result["counts"]["UNKNOWN"] >= 1


def test_pipeline_supports_contradictions():
    yes=Evidence("code.definition","code-inspector","run","a.py:1","inspector",0.9)
    no=Evidence("code.definition","review","run absent","review:1","review",0.9)
    result=analyze_observations("repo",[yes],contradictions=[no])
    assert result["findings"][0]["contradictions"]
    assert result["findings"][0]["score"] < 0.5


def test_safe_pipeline_fails_open():
    result=safe_analyze("demo",object())
    assert result["status"] == "unavailable"
    assert "error" in result

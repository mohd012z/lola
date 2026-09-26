from lola_evidence_integration import enrich_apk_analysis, enrich_code_report


def test_apk_enrichment_is_additive():
    raw={"package":"com.example.demo","urls":[{"entry":"classes.dex","offset":3,"url":"https://example.test"}]}
    result=enrich_apk_analysis(raw,"demo.apk")
    assert result["package"] == "com.example.demo"
    assert result["evidenceAnalysis"]["status"] == "ok"
    assert result["evidenceAnalysis"]["observationCount"] == 1


def test_code_enrichment_is_additive():
    raw={"python_files":1,"files":[{"file":"a.py","syntax_ok":True,"imports":[],"definitions":[{"type":"FunctionDef","name":"run","line":2}],"calls":[]}]}
    result=enrich_code_report(raw,"repo")
    assert result["python_files"] == 1
    assert result["evidenceAnalysis"]["status"] == "ok"


def test_enrichment_preserves_original_on_bad_optional_input():
    raw={"package":"com.example.demo","urls":"bad-shape"}
    result=enrich_apk_analysis(raw,"demo.apk")
    assert result["package"] == "com.example.demo"
    assert "evidenceAnalysis" in result

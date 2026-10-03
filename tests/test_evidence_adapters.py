from lola_evidence_adapters import apk_observations, code_observations


def test_apk_observations_keep_provenance_and_dedupe():
    data = {
        "urls": [
            {"entry": "classes.dex", "offset": 42, "url": "https://example.test/api", "host": "example.test", "scheme": "https"},
            {"entry": "classes.dex", "offset": 42, "url": "https://example.test/api", "host": "example.test", "scheme": "https"},
        ],
        "permissions": ["android.permission.CAMERA"],
        "components": [{"type": "activity", "name": ".MainActivity", "exported": "true"}],
    }
    rows = apk_observations(data)
    urls = [x for x in rows if x.kind == "apk.url"]
    assert len(urls) == 1
    assert urls[0].locator == "classes.dex@42"
    assert urls[0].metadata["host"] == "example.test"
    assert any(x.kind == "apk.permission" for x in rows)
    assert any(x.kind == "apk.component" for x in rows)


def test_apk_observations_accept_partial_input():
    assert apk_observations({}) == []
    assert apk_observations(None) == []


def test_code_observations_keep_file_line_provenance():
    report = {"files": [{
        "file": "pkg/demo.py",
        "syntax_ok": True,
        "imports": ["json"],
        "definitions": [{"type": "FunctionDef", "name": "run", "line": 12}],
        "calls": [{"name": "loads", "line": 13}],
    }]}
    rows = code_observations(report)
    definition = next(x for x in rows if x.kind == "code.definition")
    assert definition.locator == "pkg/demo.py:12"
    assert any(x.kind == "code.import" and x.observation == "json" for x in rows)


def test_code_observations_report_syntax_failure_as_evidence():
    report = {"files": [{"file": "bad.py", "syntax_ok": False, "line": 7, "error": "invalid syntax"}]}
    rows = code_observations(report)
    row = next(x for x in rows if x.kind == "code.syntax_error")
    assert row.locator == "bad.py:7"
    assert "invalid syntax" in row.observation

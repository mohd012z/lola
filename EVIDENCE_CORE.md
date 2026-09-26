# Lola Evidence-Driven Analysis Core

Lola's evidence layer lets conclusions carry provenance and explicit confidence instead of treating every observation as equally certain.

## Components

- `lola_evidence.py` — evidence ledger, contradictions, confidence scoring, JSON export.
- `lola_hypothesis.py` — hypothesis evaluation and missing-evidence reporting.
- `lola_evidence_adapters.py` — normalization of APK and Python-inspector observations while preserving locators.
- `lola_evidence_pipeline.py` — additive orchestration, coverage reporting, contradiction handling, and fail-open wrapper.
- `tests/test_evidence_core.py` — core confidence/hypothesis tests.
- `tests/test_evidence_adapters.py` — normalization/provenance tests.
- `tests/test_evidence_pipeline.py` — orchestration/fallback tests.

## Confidence states

`VERIFIED` → strong score with independent evidence sources.

`HIGH` → strong supporting evidence.

`PROBABLE` → useful evidence, but not enough for high confidence.

`INFERRED` → weak or incomplete evidence.

`UNKNOWN` → no supporting evidence. Lola preserves this state rather than guessing.

## Phase 2 data flow

```text
analyze-apk.py / lola_code_inspector.py
              ↓
      evidence adapters
              ↓
        Evidence records
              ↓
        EvidenceLedger
              ↓
 confidence + contradictions + missing coverage
              ↓
      additive evidenceAnalysis
```

Adapters retain `entry@offset` for APK observations and `file:line` for code observations where available. Duplicate normalized observations are removed before confidence processing so repetition from one provider does not masquerade as independent corroboration.

Evidence processing is optional. The safe pipeline returns `status=unavailable` on malformed input or evidence-layer failure; callers can retain their original analyzer output.

## Example

```python
from lola_evidence_adapters import apk_observations
from lola_evidence_pipeline import safe_analyze

raw = {"urls": [{"entry": "classes.dex", "offset": 42, "url": "https://example.test"}]}
result = safe_analyze("sample.apk", apk_observations(raw), expected_kinds={"apk.url"})
print(result)
```

## Phase 3 boundary

Ghidra/PyGhidra is intentionally not a Phase 2 dependency. It can later become an optional evidence provider feeding the same normalized ledger after the adapter/pipeline integration is verified. The core remains analysis-oriented and does not perform target modification.

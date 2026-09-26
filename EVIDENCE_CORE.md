# Lola Evidence-Driven Analysis Core

This adds a reusable analysis layer for Lola so conclusions can carry provenance and explicit confidence instead of being treated as equally certain.

## Components

- `lola_evidence.py` — evidence ledger, contradictions, confidence scoring, JSON export.
- `lola_hypothesis.py` — hypothesis evaluation and missing-evidence reporting.
- `tests/test_evidence_core.py` — unit coverage for UNKNOWN handling, independent evidence, contradictions, and missing evidence.

## Confidence states

`VERIFIED` → strong score with independent evidence sources.

`HIGH` → strong supporting evidence.

`PROBABLE` → useful evidence, but not enough for high confidence.

`INFERRED` → weak or incomplete evidence.

`UNKNOWN` → no supporting evidence. Lola should preserve this state rather than guess.

## Example

```python
from lola_evidence import Evidence, EvidenceLedger
from lola_hypothesis import cross_check

ledger = EvidenceLedger("sample.apk")
observations = [
    Evidence("manifest", "AndroidManifest.xml", "component declared", tool="apk-parser", weight=0.9),
    Evidence("code", "classes.dex", "component referenced", tool="dex-analyzer", weight=0.8),
]

result = cross_check(
    "declared component is referenced by application code",
    ledger,
    observations,
    {"manifest", "code"},
)
ledger.write("lola-evidence.json")
print(result)
```

## Integration direction

Existing Lola analyzers can emit `Evidence` records without changing their current report format. A later integration can correlate APK static analysis, runtime observations, source inspection, and Ghidra/PyGhidra-derived observations through this ledger. Ghidra supports scripting and extension development, making it suitable as an optional evidence provider rather than a hard dependency.

The core is intentionally analysis-oriented and does not perform target modification.

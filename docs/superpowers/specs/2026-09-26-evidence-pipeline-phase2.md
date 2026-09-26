# Lola Evidence Pipeline Phase 2 Specification

## Goal
Wire Lola's existing APK and Python static-analysis observations into the evidence/confidence core without changing the scanners' primary behavior or making evidence processing a hard dependency.

## Architecture
Existing analyzers remain observation producers. A new `lola_evidence_adapters.py` module normalizes their JSON/dict outputs into `Evidence` records with source, kind, locator, tool, weight, and metadata. `lola_evidence_pipeline.py` consumes normalized observations, records them in an `EvidenceLedger`, runs bounded hypotheses, and returns an additive `evidenceAnalysis` payload. Failures in this optional path are reported as unavailable/error metadata and do not invalidate the original scan result.

## Inputs
- APK analysis dictionaries produced by `analyze-apk.py`.
- Repository inspection dictionaries produced by `lola_code_inspector.py`.

## Outputs
An additive `evidenceAnalysis` object containing:
- target
- confidence counts
- findings with provenance
- contradictions where supplied
- hypothesis results
- missing-evidence declarations
- pipeline status

## Provenance rules
- APK evidence keeps the APK-analysis field and, where available, entry/path + byte/string offset.
- Code evidence keeps file + source line.
- Derived conclusions must reference normalized evidence; they must not be presented as raw observations.
- Missing evidence remains explicit and maps to UNKNOWN rather than being guessed.

## Confidence rules
Reuse `lola_evidence.py` confidence semantics. No adapter may promote confidence by fabricating a second source. Independent evidence diversity must come from genuinely distinct observations/providers.

## Failure isolation
Evidence integration is optional. Import errors, malformed optional evidence, or adapter failures must not prevent the original APK or repository inspection result from being produced.

## Phase boundary
This phase does not add Ghidra/PyGhidra, target modification, runtime instrumentation, or new offensive functionality. Ghidra is reserved for Phase 3 as an optional evidence provider.

## Verification
Tests must cover APK normalization, code-inspector normalization, provenance, missing evidence, contradiction handling, malformed/partial input, and graceful fallback. Existing tests must continue to pass.
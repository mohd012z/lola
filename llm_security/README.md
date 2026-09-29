# Lola LLM Guardrail Analysis

Defensive analysis layer inspired by public jailbreak research datasets such as `verazuo/jailbreak_llms` and standardized robustness work such as JailbreakBench.

## Scope

This subsystem is for detection, classification, evidence collection, regression testing, and guardrail evaluation. It does **not** generate, optimize, mutate, or automatically replay jailbreak payloads.

## Pipeline

```text
prompt
  -> normalize
  -> fingerprint
  -> structural detectors
  -> independent signal aggregation
  -> risk score
  -> ALLOW | REVIEW | BLOCK
  -> evidence/reporting
```

`guardrail_analyzer.py` currently detects explainable structural indicators for instruction override, role manipulation, hidden-instruction requests, safety-evasion language, and encoding/obfuscation pressure.

## Evidence-core integration

The next integration boundary is Lola's existing evidence ledger. Each `Signal` should become an evidence observation so prompt-risk conclusions inherit Lola's VERIFIED/HIGH/PROBABLE/INFERRED/UNKNOWN semantics instead of being treated as certain.

## Corpus handling

External research corpora should remain test/evaluation inputs rather than runtime dependencies. Before benchmark ingestion:

1. preserve source/license metadata;
2. sanitize personal identifiers where applicable;
3. hash/fingerprint records;
4. deduplicate exact and near-duplicate records;
5. split training/reference and regression sets;
6. store aggregate metrics rather than harmful payloads in normal reports.

## Metrics

Track at least:

- true-positive rate on labeled attack-like samples;
- false-positive / over-refusal rate on benign samples;
- precision, recall, F1;
- decision distribution;
- detector contribution by signal family;
- regression delta between releases.

A benign comparison set is essential: a detector that blocks everything is not a useful defense.

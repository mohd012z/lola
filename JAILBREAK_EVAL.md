# LOLA Jailbreak Evaluation Harness

Defensive module for analysing untrusted AI prompt samples as **data**, not instructions.

## Pipeline

```text
Untrusted prompt corpus
        |
        v
Normalization + SHA-256
        |
        v
Technique classifier
        |
        +-- role override
        +-- authority spoofing
        +-- policy replacement
        +-- instruction persistence
        +-- refusal suppression
        +-- tool coercion
        +-- context poisoning
        +-- multi-turn escalation
        |
        v
Risk score + evidence report
        |
        v
Regression corpus / human review
```

## Usage

```bash
python jailbreak_eval.py samples/
python jailbreak_eval.py samples/ --json > jailbreak-report.jsonl
```

The scanner does not execute embedded commands, call URLs, forward prompts to a model, or treat corpus content as trusted instructions.

## Recommended LOLA integration

Keep external jailbreak repositories outside LOLA source control or as explicitly reviewed test fixtures. Do not automatically execute or dynamically import their content. A future adapter can fetch a pinned revision into an isolated corpus directory, record provenance and hashes, then feed the text only to this classifier/evaluation layer.

## Evaluation goals

Use the resulting corpus to regression-test instruction hierarchy, prompt-injection resistance, tool authorization boundaries, untrusted-content handling, and multi-turn policy persistence. Store model responses separately from source prompts so evidence remains reproducible.

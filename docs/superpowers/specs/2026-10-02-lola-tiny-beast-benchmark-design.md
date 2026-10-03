# LOLA Tiny-to-Beast Benchmark — Design

## Goal
Prove or reject architecture-level intelligence gain without confusing it with a model upgrade. The benchmark compares verified before/after trials while holding model identity and hardware identity fixed.

## Claim under test
After verified learning, `kernel_ai + in_ai` can solve an unseen variant in the same problem family using a lower intellectual operating level and no greater cognitive work, without increasing false-solved or regression failures.

## Trial contract
Each trial records:
- task ID and problem family;
- transfer distance (`T0` exact repeat, `T1` parameter/near repeat, `T2+` unseen structural/environmental variation);
- exact model/build identity;
- exact hardware profile identity;
- independent verification status;
- false-solved flag;
- intellectual operating level;
- actions, escalations, tokens, wall time;
- external-AI use;
- regression failures.

## Promotion gate
A default pass requires:
1. Same problem family.
2. Same model identity.
3. Same hardware identity.
4. Baseline and learned trials independently verified.
5. Learned transfer distance >= T2.
6. Learned intellectual level lower than baseline.
7. Learned actions and escalations do not increase.
8. Recorded tokens/wall time do not increase when baseline values are present.
9. No false-solved result.
10. No regression failures.

`--require-sovereign` additionally rejects any learned trial using external AI.

## Non-claims
- A synthetic harness smoke is not empirical Tiny-to-Beast evidence.
- A larger model replacing a smaller model is not architecture intelligence gain.
- T0/T1 repetition is not sufficient generalization evidence.
- Green CI proves evaluator correctness, not frontier-level intelligence.

## Output
The evaluator exposes raw deltas and explicit rejection reasons rather than a universal IQ score. A real eligible pass reports `SYSTEM_INTELLIGENCE_GAIN`; otherwise it reports `NOT_PROVEN`.

## Safety / epistemic integrity
The benchmark consumes measured evidence. It does not grant execution authority, write durable knowledge, or promote a skill by itself. Existing transfer, verification, regression, and knowledge-lifecycle gates remain authoritative.
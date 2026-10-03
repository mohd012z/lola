# Prospective Transfer Preregistration v1

This tier exists to prevent LOLA from calling a retrospectively selected success a blind/prospective result.

## Phase A — preregistration

Before a future holdout exists, LOLA freezes:

- learned hypothesis: `preflight_validity`;
- evaluator identity and Git blob SHA;
- frozen training-fixture blob SHA;
- fixed model and hardware identities;
- holdout selection rule;
- exclusions;
- transfer threshold;
- action/intellectual downshift requirements;
- verification, sovereign, false-solved, and regression requirements;
- the claim ceiling before reveal.

The canonical contract is `fixtures/prospective_transfer_prereg_v1.json`. Its content, excluding `seal_sha256`, is canonicalized with sorted JSON keys and hashed with SHA-256. `lola_prospective_prereg.py` validates both the seal and the semantic rules.

Run:

```bash
python lola.py --prospective-transfer-prereg
```

A healthy Phase-A result is:

```text
status = SEALED_AWAITING_HOLDOUT
prospective_claim = false
blind_holdout_claim = false
production_world_claim = false
```

A preregistration pass is **not** an intelligence result. It only proves that the future test contract was frozen before its holdout was revealed.

## Holdout selection

The holdout is not chosen by whether it matches the learned rule. It is defined in advance as the **first eligible naturally occurring LOLA defect after the preregistration merge** that:

1. creates an observable CI, runtime, integration, or behavior failure;
2. has independently verifiable before/fix evidence;
3. is not benchmark-authored or intentionally injected;
4. is not documentation-only;
5. is not a benchmark fixture created for this test; and
6. is not merely the same-origin continuation of one of the training incidents.

Known-outcome selection and cherry-picking are forbidden by the sealed contract.

## Phase-B anchor rule

The merge commit that first places the sealed Phase-A manifest on `feat/hybrid-cognitive-fabric` becomes the preregistration anchor.

A future Phase-B result must be submitted separately and must reference:

- that **prior preregistration merge commit SHA**;
- the exact Phase-A contract digest;
- the evaluator blob SHA already frozen by Phase A;
- the newly observed holdout provenance and discovery time/evidence;
- fixed model/hardware identities;
- independently verified baseline and learned observations.

The Phase-B verifier must read/compare the preregistration from the referenced prior Git state. Editing the hypothesis, evaluator, selection policy, or thresholds in the same change that reveals the holdout invalidates prospective/blind status.

## Pass contract

The sealed v1 contract requires at minimum:

- T2 or greater transfer distance;
- same model;
- same hardware identity;
- sovereign/no external-AI learned run;
- verified baseline and learned outcomes;
- at least one intellectual-level downshift;
- learned action delta of at most `-1` versus baseline;
- zero regression failures;
- no false-solved outcome;
- no hypothesis/evaluator change after reveal.

Failure is valid evidence. If the first eligible holdout does not benefit from the learned abstraction, LOLA must record that negative result rather than select another holdout.

## Evidence ceiling

Until an eligible holdout occurs and Phase B is evaluated against this prior sealed registration, LOLA must remain:

```text
AWAITING_HOLDOUT
```

This protocol does not yet establish prospective or blind transfer; it establishes the conditions under which a future result may legitimately make that claim.

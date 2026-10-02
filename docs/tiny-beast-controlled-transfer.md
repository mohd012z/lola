# Tiny-to-Beast Controlled Transfer Benchmark

## Purpose

This benchmark is the first measured transfer layer above the synthetic Tiny-to-Beast harness. It exercises LOLA's real experience compiler and transfer-governance modules, then compares diagnostic work before and after governed learning on structurally varied T2/T3 tasks.

It is deliberately a **controlled empirical benchmark**, not a production-world intelligence claim.

## Execution path

```text
verified independent episodes
  -> ExperienceCompiler
  -> independent-origin/counterexample accounting
  -> transfer governance
  -> advisory abstract failure-role priority
  -> T2/T3 diagnostic execution
  -> independent verification
  -> Tiny-to-Beast fixed-model/fixed-runtime gate
```

The learned candidate never receives execution authority from governance. It only changes diagnostic ordering after the evidence gate passes.

## Current controlled result

Run:

```bash
python lola.py --controlled-transfer-benchmark
```

Initial CI measurement on Toolchain run #223:

| Trial | Transfer | Baseline actions | Learned actions | Action delta | Intellectual level | Verified | External AI | Regressions |
|---|---:|---:|---:|---:|---|---|---|---:|
| controlled-t2 | T2 | 4 | 1 | -3 | 4 -> 1 | yes | no | 0 |
| controlled-t3 | T3 | 5 | 1 | -4 | 4 -> 1 | yes | no | 0 |

Learning evidence contained two unique verified episodes from two independent origin domains. Transfer governance returned `governance_passed`, `promotable: true`, and `execution_authority: false`.

Both T2 and T3 evaluations returned `SYSTEM_INTELLIGENCE_GAIN` under the fixed `kernel-symbolic-inspector-v1` / `controlled-python-runtime` identity.

## Falsification behavior

A counterexample for the learned abstract failure role is intentionally retained by the experience compiler. When present:

1. transfer governance returns `counterexamples_unresolved`;
2. the learned priority is not applied;
3. learned action count remains equal to baseline;
4. no intellectual downshift is claimed; and
5. the Tiny-to-Beast gate rejects the result.

This prevents a known contradictory episode from being hidden by successful repetitions.

## Epistemic boundary

What this result supports:

- the current Kernel_AI/IN_AI learning architecture can compile two independent verified experiences into an advisory reusable diagnostic priority;
- that priority transfers across the controlled T2 and T3 variants;
- the fixed symbolic runtime requires fewer diagnostic inspections while preserving verification and regression checks;
- the result is sovereign in this benchmark because no external AI is used.

What this result does **not** establish:

- broad production-world generalization;
- frontier-model-equivalent reasoning;
- transfer across unrelated task families;
- improvement in model weights;
- robustness to open-ended real repository failures, noisy observations, or adversarially chosen task distributions.

The next evidence level should use frozen, independently sourced historical/real task fixtures that were not authored to match the learned rule, while preserving the same before/after instrumentation and counterexample gates.

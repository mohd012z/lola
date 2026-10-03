# LOLA Tiny-to-Beast Benchmark — Implementation Plan

1. Define the benchmark contract in RED tests before implementation.
2. Implement deterministic `BenchmarkTrial`, pair loading, and `evaluate_growth()`.
3. Require same model/hardware, T2+ transfer, verified outcomes, intellectual downshift, no false-solved, and no regression failures.
4. Add sovereign enforcement for learned trials that must not use external AI.
5. Expose a synthetic harness command: `python lola.py --tiny-beast-smoke`.
6. Expose the empirical command: `python lola.py --tiny-beast-benchmark <json> [--require-sovereign]`.
7. Add a documented example JSON fixture.
8. Add CI compile/unit/smoke coverage.
9. Verify RED→GREEN history, full Toolchain smoke, and Code Doctor on the exact branch head.
10. Open a PR against `feat/hybrid-cognitive-fabric` only after all current-head gates are green.

Completion of this plan proves the benchmark infrastructure, not the empirical Tiny-to-Beast claim. Real measured before/after trials are required for that claim.
"""Delta-observe — the prediction-error stage, backed by #42's DeltaMemory.

docs/superpowers/specs/delta-observe-and-stack-verify.md, Module S.

#42's DeltaMemory is a delta-rule associative memory: each step it reads
what the key currently recalls, stores ONLY the gap `(value - read) *
beta`, and updates its state. That "store the prediction error, not the
raw value" property is exactly the observe stage's job: the store's
recall is the FORECAST, and `observed - forecast` is the PREDICTION
ERROR. Repeated observations of a stable quantity converge the forecast
toward it — overwrite corrects, it does not duplicate.

PredictionErrorStore wraps DeltaMemory(dim=1) as a per-quantity
forecasting store. No new math — it is the reference delta rule applied
to a scalar.
"""
from __future__ import annotations

from typing import Any, Sequence

from lola_delta_memory import DecayParams, DeltaMemory

# "this quantity" basis for a dim-1 store: the single dimension is the
# quantity itself. Used as the key (k), readout query (q), and the value
# (v) carries the observation.
_BASIS = [1.0]


class PredictionErrorStore:
    """A dim-1 delta-rule store used as a prediction-error substrate.

    Decay choice: the reference GigaChat kernel defaults to a_log=0,
    dt_bias=0 (decay 0.5 per step) — appropriate for fast per-token
    forgetting in a 40-layer transformer. A scalar PREDICTION store has a
    different job: it should track a stable quantity and drive the
    prediction error to ~0 on repeated identical observations. A 0.5
    decay is a leaky integrator whose steady state sits below the signal,
    so this store defaults to a gentle decay (a=-10 -> decay ~0.99995)
    and exposes a/b so the decay/gate are tunable per use. The #42
    DeltaMemory itself is untouched and keeps kernel parity.
    """

    def __init__(self) -> None:
        self._mem = DeltaMemory(dim=1,
                                params=DecayParams(a_log=(0.0,),
                                                   dt_bias=(0.0,)))
        self._step = 0

    # gentle-decay default for a forecasting store (see class docstring)
    _A = -10.0
    _B = 4.0

    @property
    def prediction(self) -> float:
        """The store's current recall (its forecast); 0.0 when fresh.

        Read directly from the (dim-1) state — a read-only view, so
        checking the forecast never perturbs the store.
        """
        return self._mem._state[0][0]

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> "PredictionErrorStore":
        store = cls()
        store._mem = DeltaMemory.from_snapshot(snapshot,
                                               DecayParams(a_log=(0.0,),
                                                           dt_bias=(0.0,)))
        store._step = snapshot.get("steps", 0)
        return store

    def snapshot(self) -> dict:
        return self._mem.snapshot()

    def observe(self, observed: float, *, a: float | None = None,
                b: float | None = None) -> dict:
        """One recurrence step: write `observed`, return the prediction error.

        The delta rule stores `(value - read) * beta`. With value=observed
        and read=the current forecast, the stored correction IS the
        (gated) prediction error. `a`/`b` default to the store's gentle
        decay / strong write-gate (see class docstring).
        """
        a = self._A if a is None else a
        b = self._B if b is None else b
        predicted = self._mem._state[0][0]
        out, record = self._mem.step(q=_BASIS, k=_BASIS,
                                     v=[float(observed)], a=[a], b=[b])
        self._step += 1
        converged = self._mem._state[0][0]
        return {
            "step": self._step,
            "predicted": predicted,
            "observed": float(observed),
            # the TRUE signed error: what we got minus what we predicted
            "prediction_error": float(observed) - predicted,
            # the beta-scaled correction the store actually wrote
            "stored_correction": record.delta[0],
            "converged": converged,
            "decay": record.decay,
            "beta": record.beta,
        }


def run_recheck(store: PredictionErrorStore,
                observed_values: Sequence[float]) -> dict:
    """Drive a sequence of observations through the prediction-error store.

    Returns per-cycle records, the converged forecast, the summed absolute
    error, and a replayable snapshot.
    """
    cycles = []
    total_abs = 0.0
    for value in observed_values:
        rec = store.observe(float(value))
        total_abs += abs(rec["prediction_error"])
        cycles.append(rec)
    return {
        "cycles": cycles,
        "converged_prediction": store.prediction,
        "total_abs_error": total_abs,
        "snapshot": store.snapshot(),
    }

"""Delta-rule associative memory, ported from the GigaChat 3.5 GatedDeltaNet
linear-attention recurrence (see docs/superpowers/specs/gigachat-methods.md).

The reference kernel (modeling_gigachat3_5.py::torch_recurrent_gated_delta_rule):

    S <- S * g                 (decay)
    mem <- S @ k                (read: what the key currently recalls)
    delta <- (v - mem) * beta   (prediction-error write: store only the gap)
    S <- S + k (x) delta        (delta-rule update)
    out <- S @ q                (readout)

with g = -exp(A_log) * softplus(a + dt_bias) and beta = sigmoid(b).
This is the "conservative write" idea: the memory stores the *difference*
between the incoming value and what the key already predicts, not the raw
value — overwriting a key therefore corrects instead of duplicating.

Lola uses this as a deterministic, evidence-grade-neutral working store for
per-episode key/value recall. No learning, no GPU, no external deps: pure
stdlib math so the module stays unit-testable in CI exactly like the rest of
the cognitive fabric.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def softplus(x: float) -> float:
    # numerically stable for large |x|
    if x > 30.0:
        return x
    if x < -30.0:
        return 0.0
    return math.log1p(math.exp(x))


def l2norm(vec, eps: float = 1e-6):
    n = math.sqrt(sum(x * x for x in vec) + eps)
    if n <= eps:
        return [0.0] * len(vec)
    return [x / n for x in vec]


@dataclass(frozen=True)
class DecayParams:
    """Per-head discretization parameters (A_log, dt_bias) from the reference
    kernel. Length 1 applies the same scalar to every head."""

    a_log: tuple
    dt_bias: tuple

    def __post_init__(self):
        if not self.a_log or not self.dt_bias:
            raise ValueError("decay params must be non-empty")
        if len(self.a_log) not in (1, len(self.dt_bias)):
            raise ValueError("a_log and dt_bias must match in length")
        for x in (*self.a_log, *self.dt_bias):
            if not math.isfinite(x):
                raise ValueError("decay params must be finite")


@dataclass(frozen=True)
class StepRecord:
    """Audit trail for one memory step — the Lola equivalent of the
    per-token recurrent state in the reference kernel."""

    decay: float
    beta: float
    read_value: tuple
    delta: tuple
    stored_value: tuple
    output: tuple


class DeltaMemory:
    """Single-head (vector) delta-rule memory.

    ``dim`` is the key/value dimension. The recurrent state is a dim x dim
    matrix (row-major list of lists); reads/writes are plain vectors.
    """

    def __init__(self, dim: int, params: DecayParams):
        if int(dim) < 1:
            raise ValueError("dim must be positive")
        self.dim = int(dim)
        self.params = params
        self._state = [[0.0] * self.dim for _ in range(self.dim)]
        self._steps = 0

    @classmethod
    def from_snapshot(cls, snapshot, params: DecayParams) -> "DeltaMemory":
        mem = cls(snapshot["dim"], params)
        mem._state = [list(row) for row in snapshot["state"]]
        mem._steps = snapshot["steps"]
        return mem

    def snapshot(self) -> dict:
        return {
            "dim": self.dim,
            "state": [list(row) for row in self._state],
            "steps": self._steps,
        }

    # -- internals ---------------------------------------------------------

    def _check(self, name: str, vec):
        if len(vec) != self.dim:
            raise ValueError(f"{name} must have length {self.dim}, got {len(vec)}")
        for x in vec:
            if not math.isfinite(x):
                raise ValueError(f"{name} must be finite")

    def _apply(self, vec):
        # S @ vec with S stored row-major: out[i] = sum_j S[i][j] * vec[j]
        return [sum(Sij * v for Sij, v in zip(row, vec)) for row in self._state]

    def _axpy(self, k, delta):
        # S <- S + k (x) delta
        for i in range(self.dim):
            ki = k[i]
            for j in range(self.dim):
                self._state[i][j] += ki * delta[j]

    # -- public API ----------------------------------------------------------

    def step(self, *, q, k, v, a, b) -> tuple:
        """One recurrence step. Returns (output, StepRecord).

        q, k, v: vectors of length dim.
        a, b: scalars (lists of length 1 for parity with the per-head kernel).
        """
        self._check("q", q)
        self._check("k", k)
        self._check("v", v)
        if len(a) != 1 or len(b) != 1:
            raise ValueError("a and b must be length-1 lists")
        for x in (*a, *b):
            if not math.isfinite(x):
                raise ValueError("a and b must be finite")

        a_log = self.params.a_log[0]
        dt_bias = self.params.dt_bias[0]

        g = -math.exp(a_log) * softplus(a[0] + dt_bias)
        decay = math.exp(g) if g > -745.0 else 0.0
        beta = sigmoid(b[0])

        # decay state
        for i in range(self.dim):
            row = self._state[i]
            for j in range(self.dim):
                row[j] *= decay

        k_n = l2norm(k)

        read_value = self._apply(k_n)
        # NOTE: v is NOT normalized — parity with the reference kernel, which
        # applies l2norm to q and k only (use_qk_l2norm_in_kernel).
        delta = [(vi - ri) * beta for vi, ri in zip(v, read_value)]
        self._axpy(k_n, delta)
        stored_value = self._apply(k_n)
        output = self._apply(l2norm(q))

        self._steps += 1
        record = StepRecord(
            decay=decay,
            beta=beta,
            read_value=tuple(read_value),
            delta=tuple(delta),
            stored_value=tuple(stored_value),
            output=tuple(output),
        )
        return output, record

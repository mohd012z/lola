# GigaChat 3.5 Reasoning — source study and Lola method ports

Studied 2026-10-03 from the released sources: `configuration_gigachat3_5.py`,
`modeling_gigachat3_5.py`, `chat_template.jinja`, `config.json`,
`generation_config.json`, `README.md`, and the safetensors weight map of
`ai-sage/GigaChat3.5-432B-A28B-Reasoning` (Hugging Face, MIT license).
Method distilled; nothing copied (the model weights are 446 GB of FP8 tensors
and not reproducible here — only the *structures* are transferable).

## 1. What the released Reasoning checkpoint actually is

Config-vs-weights cross-check (a discrepancy the README alone would hide):

| Item | config default | released config.json | weight map |
|---|---|---|---|
| Layers | 61 | 40 | 40 (`layers.0..39`) |
| Attention heads | 128 | 64 | — |
| n_group / topk_group | 8 / 4 | 1 / 1 | — |
| Full-attention layers | — | [3,7,…,39] every 4th | `q_a_proj` only in those 10 + MTP |
| Linear-attention layers | — | — | `in_proj_qkvz` in the other 30 |
| Dense → MoE switch | first_k_dense_replace=3 | 3 | `mlp.experts` from layer 3 |
| MTP heads | num_nextn_predict_layers=3 | 3 | `layers.40..42` w/ `shared_head`, `eh_proj`, `enorm`, `hnorm` |
| Context | 4096 (default) | 262144 (YaRN ×8) | — |
| Total params | — | 432B / ~28B active | 445,994,440,544 bytes FP8 |

So the released model is **40 hybrid layers (30 GatedDeltaNet + 10 MLA,
every 4th), 3 dense MLPs then 256-expert MoE (top-8) with 1 shared expert,
and 3 dedicated MTP layers appended after the trunk** (each MTP layer
predicts the next token from the previous hidden state `eh_proj` +
normalized previous hidden `enorm`/`hnorm` and carries its own shared_head
draft scorer). The `num_hidden_layers=61`/`n_group=8` numbers in the
defaulted config are the *training-time* shape; the release is a distilled
40-layer form — worth remembering when comparing papers.

## 2. Mechanisms (what the code shows)

### 2.1 Gated DeltaNet — the delta-rule memory write
`torch_recurrent_gated_delta_rule` (prefill: `torch_chunk_gated_delta_rule`):

```
S ← S · g                     # multiplicative decay, g = -exp(A_log)·softplus(a + dt_bias)
mem ← S @ k                    # read: what the key currently recalls
δ ← (v − mem) · β             # β = sigmoid(b): store ONLY the prediction error
S ← S + k ⊗ δ                  # rank-1 delta update
out ← S @ q
```

`l2norm` is applied to **q and k only, never v** (the kernel flag
`use_qk_l2norm_in_kernel`). The recurrent state is a *fixed-size* matrix per
head regardless of sequence length — that is the "262K context for the price
of a constant memory" claim. The delta rule (store `v − S@k`, not raw `v`)
makes repeated writes to the same key **correct** the stored value instead of
accumulating duplicates. The 4-conv-kernel short conv (`linear_conv_kernel_dim=4`)
pre-processes the mixed QKV stream before the recurrence.

### 2.2 MLA with split position encoding
`GigaChat35Attention`: q is compressed through `q_a_proj → q_a_layernorm →
q_b_proj` (rank 1536), kv through `kv_a_proj_with_mqa → norm → kv_b_proj`
(rank 512). Each head's dim splits into **nope (128, no position) + rope
(64, positional)**; only the rope half gets RoPE. `use_mla_scaling_factor`
rescales by `sqrt(hidden/rank)` to keep attention variance stable.
`gated_attention=True` multiplies the attention output by
`sigmoid(gate_proj(x))` — a per-token output gate on top of the softmax.

### 2.3 GatedNorm (learned multiplicative gate after RMSNorm)
`ZeroCenteredGatedNorm`: `out = RMSNorm(x)·(1+w) · 2.0 · sigmoid(W₂·SiLU(W₁·x̂))`
where the gate is a **16-dim bottleneck** (not per-element). Every layernorm
in the release (including inside attention q/kv projections and the MTP
heads) is of this gated variety — the norm itself is content-conditional.

### 2.4 Router: sigmoid top-k, no softmax
`GigaChat35TopkRouter`: scores = `sigmoid(Wx)` (NOT softmax), group-top-k
pruning (top 2 per group summed → top groups kept), then top-8 over the
mask, weights renormalized (`norm_topk_prob`) and scaled by
`routed_scaling_factor=2.5`. The load-balancing correction bias buffer
(`e_score_correction_bias`) is present but zeroed at inference. Sigmoid
scoring decouples expert selection from the other experts' scores —
selection is an independent per-expert gate, which is why 256 experts can
coexist without softmax interference.

### 2.5 chatml v5 — the *forced* reasoning layout
The template is the most transferable artifact. Its invariants:

1. **Every** assistant turn carries a `think` block; missing reasoning
   renders an **empty** block — the layout never varies between samples
   (trainable-layout stability).
2. A think block **must** be followed by text and/or tool calls;
   reasoning-only or empty turns raise at render time.
3. Turn composite order: `think` → text → `tool_calls`, joined by `\n\n`.
4. **History retention policy**: assistant turns *before* the last user
   message drop their thinking; turns on/after the last user message keep it
   (`drop_history_thinking` + `last_user_idx`).
5. The generation prompt **always** ends with the forced opener
   `assistant<role_sep>\n<think` — no opt-out of thinking.
6. Consecutive tool-result messages are **aggregated** into one
   `function result` turn, matched positionally against the preceding tool
   call names (`message.name` deliberately ignored).
7. Tool schemas are rendered as TypeScript types into a
   `function descriptions` message (compile-time-shaped contract).

### 2.6 Post-training (README, cross-checked against the 6-specialist design)
SFT → six domain specialists (STEM / Code / Code-Agent / General-Agent /
Dialogue / Soft-Skills) each with its **own reward family** (answer
verification, code execution, post-patch tests, environment state, LLM
judge side-by-side, format verification) → **CISPO** with a **task pool that
removes anything solved >75%** of attempts (difficulty climbs over training)
→ **on-policy distillation (OPD)** to merge the specialists (student
generates its own trajectory; the domain expert supplies token-level
supervision on it). Reasoning-token efficiency: 23–41% fewer reasoning
tokens than DeepSeek V4 Flash Preview on the math suites.

## 3. What Lola ports (this PR)

Two mechanisms, chosen because they are *deterministic, stdlib-only, and
governance-compatible* with the existing cognitive fabric:

### 3.1 `lola_delta_memory.py` — DeltaMemory
Single-head port of the 2.1 recurrence: decay → read → delta-write →
readout, with `l2norm` on q/k only (parity with the reference kernel),
stable sigmoid/softplus, a per-step `StepRecord` audit trail (the Lola
evidence-philosophy equivalent of the per-token recurrent state),
`snapshot()`/`from_snapshot()` for deterministic replay, and hard
validation (shape, finiteness, param consistency). No learning, no
mutation outside the object's own state, no external deps.

Usage shape: per-episode working store — key = normalized episode
fingerprint features, value = predicted-outcome vector; the readback is
what the memory *currently expects* before the correction lands, which is
exactly the "expected vs actual" signal `lola_reasoning_delta` consumes.

### 3.2 `lola_reasoning_layout.py` — chatml v5 layout invariants
`render_assistant_turn` (think→text→tool_calls, empty-turn and
reasoning-only rejection, forced empty think block),
`apply_history_policy` (drop thinking before the last user message),
`build_generation_prompt` (always ends with the forced `<think` opener).
Gives Lola one canonical, parseable transcript shape for its own
reasoning/evidence records — mirrors the `reasoning_content`/`content`
split the serving parsers expect.

### 3.3 Deliberately NOT ported
- 432B scale, 256 experts, MLA internals, GatedNorm internals, FP8
  training, YaRN — neural scaling machinery, not application architecture.
- The 6-specialist RL pipeline — requires a training rig; the *idea*
  (domain-specific rewards + >75%-solve pruning + OPD consolidation) is
  recorded here as the reference for any future offline-evaluation design.

## 4. Verification

- `tests/test_gigachat_methods.py` — 15 checks: recurrence math against the
  closed form (decay = exp(−softplus(a+dt)), β = sigmoid(b)), eps
  normalization parity, shape/finiteness rejection, snapshot replay
  determinism, layout invariants 1–5 above, history policy, tool-call
  rendering.
- Full suite + compile gate via CI (`Lola Bot Health`).

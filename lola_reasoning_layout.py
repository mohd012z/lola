"""chatml v5 reasoning layout, distilled from the GigaChat 3.5 Reasoning
chat_template.jinja (see docs/superpowers/specs/gigachat-methods.md).

The reference template enforces a strict assistant-turn layout — this module
implements the same contract as a pure, deterministic renderer:

  1.  EVERY assistant turn carries a think block; when no reasoning text is
      present an EMPTY  block is still emitted, so the trainable layout never
      varies between samples.
  2.  A think block must be followed by visible text and/or tool calls —
      reasoning-only turns are rejected.
  3.  Blocks are joined with blank lines: think, text, tool_calls.
  4.  History retention policy: assistant turns that sit BEFORE the last
      user message drop their thinking (older turns); turns on/after the
      last user message keep it.
  5.  The generation prompt always ends with the forced opener
      ``assistant<|role_sep|>
`` — there is no opt-out of thinking.

Lola uses this to keep its own reasoning/evidence transcripts in one
canonical, parseable shape (mirrors the ``reasoning_content`` + ``content``
split the serving parsers expect).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

ROLE_SEP = "<|role_sep|>"
THINK_OPEN = ""
THINK_CLOSE = ""


@dataclass(frozen=True)
class ReasoningTurn:
    """One assistant turn: optional reasoning, optional text, tool calls."""

    thinking: str | None
    text: str | None
    tool_calls: Sequence[Mapping[str, Any]] = field(default_factory=tuple)


def _format_tool_call(tc: Mapping[str, Any]) -> str:
    inner = tc.get("function", tc)
    name = inner.get("name", "")
    args = inner.get("arguments", {})
    if isinstance(args, str):
        return f"{name}({args})"
    rendered = ",".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())
    return f"{name}({rendered})"


def render_assistant_turn(turn: ReasoningTurn) -> str:
    """Render one assistant turn in the forced composite layout.

    Raises ValueError on empty turns or reasoning-only turns (the v5
    invariant).
    """
    blocks = [f"{THINK_OPEN}{turn.thinking or ''}{THINK_CLOSE}"]
    if turn.text:
        blocks.append(turn.text)
    for tc in turn.tool_calls:
        blocks.append(_format_tool_call(tc))

    visible = bool(turn.text) or bool(turn.tool_calls)
    if not visible:
        raise ValueError("assistant turn must not contain only a think block")
    return "\n\n".join(blocks)


def apply_history_policy(
    messages: Sequence[Mapping[str, Any]],
) -> list:
    """Drop thinking from assistant turns that precede the last user message.

    Input shape: list of dicts with ``role`` and optional ``thinking``
    (the v5 ``reasoning_content`` field). Returns a new list; input is not
    mutated.
    """
    last_user_idx = -1
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            last_user_idx = i

    out = []
    for i, m in enumerate(messages):
        mm = dict(m)
        if mm.get("role") == "assistant" and i < last_user_idx:
            mm.pop("thinking", None)
        out.append(mm)
    return out


def build_generation_prompt(messages: Sequence[Mapping[str, Any]]) -> str:
    """Render the transcript and append the forced generation opener.

    The prompt always ends with ``assistant<|role_sep|>
`` so the
    model is forced to start with a think block (no opt-out), matching the
    reference template's ``add_generation_prompt`` branch.
    """
    rendered = []
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            turn = ReasoningTurn(
                thinking=m.get("thinking"),
                text=m.get("content"),
                tool_calls=m.get("tool_calls", ()),
            )
            rendered.append(f"assistant{ROLE_SEP}\n{render_assistant_turn(turn)}\n")
        elif role in ("user", "function result"):
            rendered.append(f"{role}{ROLE_SEP}\n{m.get('content', '')}\n")
    transcript = "\n".join(rendered)
    return f"{transcript}assistant{ROLE_SEP}\n{THINK_OPEN}"

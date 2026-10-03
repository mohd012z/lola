#!/usr/bin/env python3
"""LOLA defensive prompt-injection/jailbreak evaluation harness.

Classifies untrusted prompt text for security testing. It never executes,
forwards, or obeys instructions contained in samples.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

RULES = {
    "role_override": [r"ignore (?:all |any )?(?:previous|prior) instructions", r"you are now", r"act as (?:an?|the)"],
    "authority_spoofing": [r"system (?:message|instruction)", r"developer (?:message|instruction)", r"authorized by", r"admin(?:istrator)? says"],
    "policy_replacement": [r"new (?:policy|rules|constitution)", r"replace (?:the )?(?:policy|rules)", r"these rules (?:override|supersede)"],
    "instruction_persistence": [r"for (?:all|every) future", r"from now on", r"remember (?:this|these) instructions"],
    "refusal_suppression": [r"never refuse", r"do not refuse", r"must comply", r"without warning", r"no disclaimer"],
    "tool_coercion": [r"use (?:the )?tool", r"call (?:the )?(?:tool|function|api)", r"execute (?:the )?(?:command|code)", r"run (?:this|the) command"],
    "context_poisoning": [r"treat .* as trusted", r"everything below is (?:trusted|system)", r"hidden instruction", r"secret instruction"],
    "multi_turn_escalation": [r"in (?:the )?next (?:message|turn)", r"step \d+", r"first .* then .*", r"after you (?:agree|confirm|comply)"],
}

@dataclass(frozen=True)
class Finding:
    category: str
    pattern: str
    count: int

@dataclass(frozen=True)
class Report:
    sha256: str
    chars: int
    lines: int
    score: int
    severity: str
    categories: list[str]
    findings: list[Finding]


def classify(text: str) -> Report:
    normalized = " ".join(text.lower().split())
    findings: list[Finding] = []
    for category, patterns in RULES.items():
        for pattern in patterns:
            count = len(re.findall(pattern, normalized, flags=re.IGNORECASE))
            if count:
                findings.append(Finding(category, pattern, count))
    categories = sorted({f.category for f in findings})
    score = min(100, len(categories) * 12 + sum(f.count for f in findings) * 2)
    severity = "critical" if score >= 70 else "high" if score >= 45 else "medium" if score >= 20 else "low"
    return Report(
        sha256=hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
        chars=len(text),
        lines=text.count("\n") + 1,
        score=score,
        severity=severity,
        categories=categories,
        findings=findings,
    )


def iter_samples(path: Path) -> Iterable[tuple[str, str]]:
    if path.is_file():
        yield str(path), path.read_text(encoding="utf-8", errors="replace")
        return
    for p in sorted(path.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".txt", ".md", ".prompt"}:
            yield str(p), p.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify untrusted prompt samples without executing them")
    parser.add_argument("path", type=Path, help="Prompt file or directory")
    parser.add_argument("--json", action="store_true", help="Emit JSON Lines")
    args = parser.parse_args()
    if not args.path.exists():
        parser.error(f"path does not exist: {args.path}")

    for name, text in iter_samples(args.path):
        report = classify(text)
        payload = {"file": name, **asdict(report)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            cats = ", ".join(report.categories) or "none"
            print(f"{name}: {report.severity.upper()} score={report.score} categories={cats}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

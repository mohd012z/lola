"""Sanitized corpus ingestion for defensive LLM-security evaluation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable, Mapping, Any


@dataclass(frozen=True)
class CorpusRecord:
    fingerprint: str
    text: str
    label: str
    source: str = "corpus"


def normalize(text: str) -> str:
    return " ".join(str(text).replace("\x00", " ").split())


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


class CorpusAdapter:
    """Normalize and exact-deduplicate corpus rows without executing content."""

    def from_rows(self, rows: Iterable[Mapping[str, Any]]) -> list[CorpusRecord]:
        seen: set[str] = set()
        output: list[CorpusRecord] = []
        for row in rows:
            text = normalize(str(row.get("prompt", "")))
            if not text:
                continue
            fp = fingerprint(text)
            if fp in seen:
                continue
            seen.add(fp)
            output.append(CorpusRecord(fp, text, str(row.get("label", "unknown")), str(row.get("source", "corpus"))))
        return output

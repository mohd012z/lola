"""Minimal code-intelligence graph and stable source locators.

This module stores observations only; it never executes inspected source files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class OffsetRef:
    path: str
    source_sha256: str
    byte_start: int
    byte_end: int
    line_start: int
    line_end: int
    symbol: str = ""


@dataclass(frozen=True)
class CodeNode:
    node_id: str
    kind: str
    name: str
    location: OffsetRef


@dataclass(frozen=True)
class CodeEdge:
    source: str
    target: str
    relation: str


@dataclass
class CodeGraph:
    nodes: dict[str, CodeNode] = field(default_factory=dict)
    edges: list[CodeEdge] = field(default_factory=list)

    def add_node(self, node: CodeNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: CodeEdge) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise ValueError("edge endpoints must exist before the edge is added")
        self.edges.append(edge)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_ref(path: str | Path, data: bytes) -> OffsetRef:
    """Create a whole-file locator without executing or importing the file."""
    text = data.decode("utf-8", errors="replace")
    lines = text.count("\n") + (1 if text else 0)
    return OffsetRef(
        path=str(path),
        source_sha256=sha256_bytes(data),
        byte_start=0,
        byte_end=len(data),
        line_start=1 if text else 0,
        line_end=lines,
    )

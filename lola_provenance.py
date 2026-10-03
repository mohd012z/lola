#!/usr/bin/env python3
"""Deterministic artifact derivation and provenance DAG for LOLA."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from lola_security_contracts import ArtifactContext, Taint


@dataclass(frozen=True)
class ProvenanceEdge:
    parent_artifact_id: str
    child_artifact_id: str
    transformation: str


class ProvenanceGraph:
    def __init__(self) -> None:
        self._artifacts: dict[str, ArtifactContext] = {}
        self._edges: list[ProvenanceEdge] = []

    def add_root(self, artifact: ArtifactContext) -> None:
        if artifact.parent_artifact_id is not None:
            raise ValueError("root artifact cannot have a parent")
        self._insert(artifact)

    def add_derived(self, artifact: ArtifactContext, transformation: str) -> None:
        parent_id = artifact.parent_artifact_id
        if not parent_id or parent_id not in self._artifacts:
            raise ValueError("derived artifact requires a known parent")
        if not transformation:
            raise ValueError("derived artifact requires a transformation")
        self._insert(artifact)
        self._edges.append(ProvenanceEdge(parent_id, artifact.artifact_id, transformation))

    def _insert(self, artifact: ArtifactContext) -> None:
        existing = self._artifacts.get(artifact.artifact_id)
        if existing is not None and existing != artifact:
            raise ValueError(f"artifact id collision: {artifact.artifact_id}")
        self._artifacts[artifact.artifact_id] = artifact

    def get(self, artifact_id: str) -> ArtifactContext:
        return self._artifacts[artifact_id]

    def lineage(self, artifact_id: str) -> tuple[ArtifactContext, ...]:
        current = self.get(artifact_id)
        chain = [current]
        seen = {current.artifact_id}
        while current.parent_artifact_id:
            parent = self.get(current.parent_artifact_id)
            if parent.artifact_id in seen:
                raise ValueError("provenance cycle detected")
            seen.add(parent.artifact_id)
            chain.append(parent)
            current = parent
        chain.reverse()
        return tuple(chain)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifacts": {
                key: _artifact_to_dict(value)
                for key, value in sorted(self._artifacts.items())
            },
            "edges": [asdict(edge) for edge in self._edges],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


def _artifact_to_dict(artifact: ArtifactContext) -> dict[str, Any]:
    data = asdict(artifact)
    data["taints"] = sorted(t.value for t in artifact.taints)
    data["transformation_chain"] = list(artifact.transformation_chain)
    return data


def derive_artifact(
    parent: ArtifactContext,
    payload: Any,
    transformation: str,
    source_id: str,
    *,
    artifact_id: str | None = None,
    source_type: str = "DERIVED_ARTIFACT",
    extra_taints: frozenset[Taint] | None = None,
) -> ArtifactContext:
    if not transformation.strip():
        raise ValueError("transformation must not be empty")
    derived_id = artifact_id or f"{parent.artifact_id}:{transformation}:{source_id}"
    return ArtifactContext.from_payload(
        artifact_id=derived_id,
        project_id=parent.project_id,
        source_type=source_type,
        source_id=source_id,
        payload=payload,
        parent=parent,
        transformation=transformation,
        taints=extra_taints,
    )

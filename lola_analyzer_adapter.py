#!/usr/bin/env python3
"""Compatibility adapter joining legacy LOLA analyzers to security/provenance.

The adapter is deliberately additive: legacy analyzer output can remain unchanged
while callers obtain an ArtifactContext, TrustEnvelope and evidence-safe metadata.
Artifact text is always treated as data, never as authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lola_provenance import derive_artifact
from lola_security import TrustEnvelope, detect_flags, envelope
from lola_security_contracts import ArtifactContext, Taint


@dataclass(frozen=True)
class AnalyzerSecurityContext:
    artifact: ArtifactContext
    trust: TrustEnvelope

    def metadata(self) -> dict[str, Any]:
        text = self.trust.payload if isinstance(self.trust.payload, str) else repr(self.trust.payload)
        reasons, risk_score = detect_flags(text)
        return {
            "artifact_id": self.artifact.artifact_id,
            "project_id": self.artifact.project_id,
            "source_type": self.artifact.source_type,
            "source_id": self.artifact.source_id,
            "content_hash": self.artifact.content_hash,
            "parent_artifact_id": self.artifact.parent_artifact_id,
            "parent_content_hash": self.artifact.parent_content_hash,
            "transformation_chain": list(self.artifact.transformation_chain),
            "taints": sorted(x.value for x in self.artifact.taints),
            "trust_state": self.trust.trust_level.value,
            "risk_score": risk_score,
            "detector_reasons": list(reasons),
        }


def artifact_context(
    *,
    artifact_id: str,
    project_id: str,
    source_type: str,
    source_id: str,
    payload: Any,
    parent: ArtifactContext | None = None,
    transformation: str | None = None,
) -> ArtifactContext:
    taints = frozenset({Taint.UNTRUSTED, Taint.EXTERNAL})
    if parent is not None:
        return derive_artifact(
            parent,
            payload,
            transformation or "analyzer-transform",
            source_id,
            artifact_id=artifact_id,
            source_type=source_type,
            extra_taints=taints,
        )
    return ArtifactContext.from_payload(
        artifact_id=artifact_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        payload=payload,
        taints=taints,
    )


def secure_artifact(
    *,
    artifact_id: str,
    project_id: str,
    source_type: str,
    source_id: str,
    payload: Any,
    parent: ArtifactContext | None = None,
    transformation: str | None = None,
) -> AnalyzerSecurityContext:
    artifact = artifact_context(
        artifact_id=artifact_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        payload=payload,
        parent=parent,
        transformation=transformation,
    )
    trust = envelope(
        payload if isinstance(payload, str) else repr(payload),
        source_type,
        source_id,
        trusted=False,
        externally_supplied=True,
    )
    return AnalyzerSecurityContext(artifact=artifact, trust=trust)


def secure_file(path: str | Path, *, project_id: str, source_type: str) -> AnalyzerSecurityContext:
    target = Path(path)
    payload = target.read_bytes()
    return secure_artifact(
        artifact_id=f"{source_type.lower()}:{target.name}",
        project_id=project_id,
        source_type=source_type,
        source_id=str(target),
        payload=payload,
    )

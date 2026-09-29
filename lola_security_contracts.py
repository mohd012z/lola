#!/usr/bin/env python3
"""Typed security contracts shared across LOLA security/intelligence planes."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Taint(str, Enum):
    UNTRUSTED = "untrusted"
    DERIVED_FROM_UNTRUSTED = "derived_from_untrusted"
    INSTRUCTION_BEARING = "instruction_bearing"
    EXECUTABLE = "executable"
    EXTERNAL = "external"


class Capability(str, Enum):
    READ_ARTIFACT = "read_artifact"
    DECODE_LOCAL = "decode_local"
    TRANSFORM_LOCAL = "transform_local"
    WRITE_LOCAL_REPORT = "write_local_report"
    MEMORY_WRITE_PROJECT = "memory_write_project"
    MEMORY_PROMOTE_GLOBAL = "memory_promote_global"
    NETWORK_REQUEST = "network_request"
    EXTERNAL_ACTION = "external_action"


class ContractActionClass(str, Enum):
    READ = "read"
    TRANSFORM = "transform"
    MEMORY_WRITE = "memory_write"
    SIDE_EFFECT = "side_effect"


def _canonical_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def content_digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_payload(payload).encode("utf-8", errors="replace")).hexdigest()


@dataclass(frozen=True)
class ArtifactContext:
    artifact_id: str
    project_id: str
    source_type: str
    source_id: str
    content_hash: str
    parent_artifact_id: str | None = None
    parent_content_hash: str | None = None
    transformation_chain: tuple[str, ...] = ()
    taints: frozenset[Taint] = field(default_factory=frozenset)

    @classmethod
    def from_payload(
        cls,
        *,
        artifact_id: str,
        project_id: str,
        source_type: str,
        source_id: str,
        payload: Any,
        parent: "ArtifactContext | None" = None,
        transformation: str | None = None,
        taints: frozenset[Taint] | None = None,
    ) -> "ArtifactContext":
        inherited = set(parent.taints if parent else ())
        if parent and Taint.UNTRUSTED in inherited:
            inherited.add(Taint.DERIVED_FROM_UNTRUSTED)
        inherited.update(taints or ())
        chain = parent.transformation_chain if parent else ()
        if transformation:
            chain = (*chain, transformation)
        return cls(
            artifact_id=artifact_id,
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            content_hash=content_digest(payload),
            parent_artifact_id=parent.artifact_id if parent else None,
            parent_content_hash=parent.content_hash if parent else None,
            transformation_chain=chain,
            taints=frozenset(inherited),
        )


@dataclass(frozen=True)
class SecurityFinding:
    detector_id: str
    detector_version: str
    category: str
    artifact_id: str
    evidence_refs: tuple[str, ...] = ()
    confidence: float | None = None
    features: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionRequest:
    name: str
    action_class: ContractActionClass
    requested_capabilities: frozenset[Capability] = field(default_factory=frozenset)
    scope: str = "local"
    target: str = ""
    authorization_source: str | None = None
    trace_id: str = ""

    def requires(self, capability: Capability) -> bool:
        return capability in self.requested_capabilities

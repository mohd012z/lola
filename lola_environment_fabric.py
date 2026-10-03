"""LOLA Environment Fabric v1.

Deterministic contracts for selecting an execution environment without granting
execution authority.  Task state remains outside disposable workers.  This
module deliberately performs no shell/network execution; providers implement
that boundary later behind AuthorityKernel policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Tuple


class EnvironmentClass(str, Enum):
    NONE = "NONE"
    MICRO = "MICRO"
    DEV = "DEV"
    BUILD = "BUILD"
    ANALYSIS = "ANALYSIS"
    ISOLATED = "ISOLATED"


class NetworkMode(str, Enum):
    OFF = "OFF"
    RESTRICTED = "RESTRICTED"


@dataclass(frozen=True)
class ResourceBudget:
    ram_mb: int = 256
    cpu_units: int = 1
    disk_mb: int = 256
    wall_time_s: int = 60
    network_bytes: int = 0

    def validate(self) -> None:
        values = (self.ram_mb, self.cpu_units, self.disk_mb, self.wall_time_s, self.network_bytes)
        if any(value < 0 for value in values):
            raise ValueError("resource budgets cannot be negative")
        if self.cpu_units == 0 or self.wall_time_s == 0:
            raise ValueError("cpu_units and wall_time_s must be positive")


@dataclass(frozen=True)
class MountSpec:
    path: str
    access: str = "READ_ONLY"

    def validate(self) -> None:
        if not self.path.startswith("/"):
            raise ValueError("mount path must be absolute")
        if self.access not in {"READ_ONLY", "READ_WRITE", "WRITE_ONLY"}:
            raise ValueError("invalid mount access")


@dataclass(frozen=True)
class EnvironmentRequest:
    task_id: str
    workload: str
    untrusted_input: bool = False
    needs_execution: bool = True
    needs_build: bool = False
    needs_analysis: bool = False
    needs_network: bool = False
    allowed_hosts: Tuple[str, ...] = field(default_factory=tuple)
    toolchains: Tuple[str, ...] = field(default_factory=tuple)
    mounts: Tuple[MountSpec, ...] = field(default_factory=tuple)
    budget: ResourceBudget = field(default_factory=ResourceBudget)


@dataclass(frozen=True)
class EnvironmentManifest:
    task_id: str
    environment_class: EnvironmentClass
    network_mode: NetworkMode
    allowed_hosts: Tuple[str, ...]
    toolchains: Tuple[str, ...]
    mounts: Tuple[MountSpec, ...]
    budget: ResourceBudget
    credentials_present: bool = False
    execution_authority: bool = False
    persistence: str = "TASK"

    def validate(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id is required")
        self.budget.validate()
        for mount in self.mounts:
            mount.validate()
        if self.network_mode is NetworkMode.OFF and self.allowed_hosts:
            raise ValueError("OFF network cannot have allowed hosts")
        if self.network_mode is NetworkMode.RESTRICTED and not self.allowed_hosts:
            raise ValueError("RESTRICTED network requires explicit hosts")
        if self.credentials_present:
            raise ValueError("long-lived credentials must remain outside workers")
        if self.execution_authority:
            raise ValueError("environment manifests never grant execution authority")


@dataclass(frozen=True)
class EnvironmentIdentity:
    environment_id: str
    task_id: str
    environment_class: EnvironmentClass
    manifest_hash: str
    policy_hash: str


@dataclass(frozen=True)
class EnvironmentObservation:
    environment_id: str
    task_id: str
    kind: str
    success: bool
    evidence_ids: Tuple[str, ...] = field(default_factory=tuple)
    metrics: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceSnapshot:
    snapshot_id: str
    task_id: str
    environment_id: str
    parent_snapshot_id: str | None = None
    artifact_refs: Tuple[str, ...] = field(default_factory=tuple)
    evidence_ids: Tuple[str, ...] = field(default_factory=tuple)


def classify_environment(request: EnvironmentRequest) -> EnvironmentClass:
    """Choose the smallest environment that satisfies the workload.

    Security dominates convenience: untrusted content always routes to the
    isolated class.  Classification is deterministic and carries no authority.
    """
    if request.untrusted_input:
        return EnvironmentClass.ISOLATED
    if not request.needs_execution:
        return EnvironmentClass.NONE
    if request.needs_build:
        return EnvironmentClass.BUILD
    if request.needs_analysis:
        return EnvironmentClass.ANALYSIS
    workload = request.workload.strip().upper()
    if workload in {"HASH", "JSON", "TEXT", "INDEX", "CALC", "MICRO"}:
        return EnvironmentClass.MICRO
    return EnvironmentClass.DEV


def plan_environment(request: EnvironmentRequest) -> EnvironmentManifest:
    """Produce a least-privilege manifest for AuthorityKernel review."""
    env_class = classify_environment(request)
    network_mode = NetworkMode.RESTRICTED if request.needs_network else NetworkMode.OFF
    allowed_hosts = tuple(dict.fromkeys(request.allowed_hosts)) if request.needs_network else ()

    # Untrusted workloads start network-dark even when the task asks for network.
    # A later AuthorityKernel decision may issue a narrower replacement manifest.
    if env_class is EnvironmentClass.ISOLATED:
        network_mode = NetworkMode.OFF
        allowed_hosts = ()

    manifest = EnvironmentManifest(
        task_id=request.task_id,
        environment_class=env_class,
        network_mode=network_mode,
        allowed_hosts=allowed_hosts,
        toolchains=tuple(dict.fromkeys(request.toolchains)),
        mounts=request.mounts,
        budget=request.budget,
    )
    manifest.validate()
    return manifest


def validate_entitlement(
    manifest: EnvironmentManifest,
    *,
    authorized_capabilities=(),
) -> tuple[bool, tuple[str, ...]]:
    """Validate declared environment needs against external entitlements.

    This function verifies entitlement; it does not mint or expand it.
    """
    manifest.validate()
    authorized = set(map(str, authorized_capabilities))
    required = set()
    if manifest.environment_class is not EnvironmentClass.NONE:
        required.add("environment.execute")
    if manifest.network_mode is NetworkMode.RESTRICTED:
        required.add("network.restricted")
    if any(m.access in {"READ_WRITE", "WRITE_ONLY"} for m in manifest.mounts):
        required.add("workspace.write")
    missing = tuple(sorted(required - authorized))
    return (not missing, missing)


def environment_360(manifest: EnvironmentManifest) -> dict[str, object]:
    """Deterministic /360 projection for observability and review."""
    manifest.validate()
    return {
        "target": manifest.task_id,
        "structure": manifest.environment_class.value,
        "data": [m.path for m in manifest.mounts],
        "dependencies": list(manifest.toolchains),
        "storage": manifest.persistence,
        "network": manifest.network_mode.value,
        "security": {
            "credentials_present": manifest.credentials_present,
            "execution_authority": manifest.execution_authority,
        },
        "runtime": {
            "ram_mb": manifest.budget.ram_mb,
            "cpu_units": manifest.budget.cpu_units,
            "wall_time_s": manifest.budget.wall_time_s,
        },
        "validation": "ENTITLEMENT_REQUIRED",
    }


def environment_7d(manifest: EnvironmentManifest) -> dict[str, object]:
    """Seven-dimensional projection: structure, behavior, data, dependencies,
    sequence/time, trust, and evidence/validation.
    """
    manifest.validate()
    return {
        "structure": manifest.environment_class.value,
        "behavior": "DISPOSABLE_WORKER",
        "data": tuple(m.path for m in manifest.mounts),
        "dependencies": manifest.toolchains,
        "time_sequence": {"persistence": manifest.persistence, "wall_time_s": manifest.budget.wall_time_s},
        "security_trust": {"network": manifest.network_mode.value, "credentials": "OUTSIDE_WORKER"},
        "evidence_validation": "OBSERVATION_REQUIRED_BEFORE_VERIFIED_RESULT",
    }

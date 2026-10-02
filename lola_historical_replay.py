"""Provenance-pinned historical replay diagnostics for LOLA.

Historical replay asks a narrower question than transfer benchmarking: can the
current diagnostic logic reproduce a documented past root cause on the frozen
pre-fix evidence and stop flagging it on the frozen repaired evidence?
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE = ROOT / "fixtures" / "historical_scanner_cwd_v1.json"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_scanner_cwd_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "historical-replay-v1":
        raise ValueError("unsupported historical replay schema")

    source = payload.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("fixture source provenance is required")
    for key in ("before_sha", "fix_sha", "before_blob_sha", "fixed_blob_sha"):
        value = str(source.get(key, ""))
        if not _SHA40.fullmatch(value):
            raise ValueError(f"invalid provenance SHA: {key}")

    incident = payload.get("incident")
    if not isinstance(incident, Mapping) or incident.get("transfer_evidence") is not False:
        raise ValueError("historical replay fixture must not claim transfer evidence")

    helpers = payload.get("critical_helpers")
    if not isinstance(helpers, list) or not helpers or not all(isinstance(x, str) and x for x in helpers):
        raise ValueError("critical_helpers must be a non-empty string list")

    for state in ("before", "after"):
        snapshot = payload.get(state)
        if not isinstance(snapshot, Mapping):
            raise ValueError(f"missing {state} snapshot")
        excerpt = str(snapshot.get("excerpt", ""))
        digest = str(snapshot.get("excerpt_sha256", ""))
        if not _SHA64.fullmatch(digest) or _sha256_text(excerpt) != digest:
            raise ValueError(f"{state} excerpt provenance digest mismatch")

    return payload


def analyze_scanner_path_resolution(excerpt: str, critical_helpers: list[str]) -> dict[str, Any]:
    """Detect CWD-coupled helper/config resolution without executing PowerShell."""
    direct_helpers = []
    for helper in critical_helpers:
        quoted = re.escape(f'"{helper}"')
        direct_test = re.search(r"Test-Path\s+-LiteralPath\s+" + quoted, excerpt) is not None
        direct_exec = re.search(r"&\s+\$Python\.Source\s+" + quoted, excerpt) is not None
        direct_array = re.search(r"@\(\s*" + quoted, excerpt) is not None
        helper_resolved = f'Resolve-LolaHelper "{helper}"' in excerpt
        if (direct_test or direct_exec or direct_array) and not helper_resolved:
            direct_helpers.append(helper)

    config_script_root_fallback = (
        "Join-Path $PSScriptRoot $Config" in excerpt
        and "Test-Path -LiteralPath $Fallback" in excerpt
    )
    helper_script_root_resolver = (
        "function Resolve-LolaHelper" in excerpt
        and "Join-Path $PSScriptRoot $Name" in excerpt
    )
    known_defect_detected = bool(direct_helpers) or not config_script_root_fallback

    return {
        "known_defect_detected": known_defect_detected,
        "cwd_relative_helper_count": len(direct_helpers),
        "cwd_relative_helpers": direct_helpers,
        "config_script_root_fallback": config_script_root_fallback,
        "helper_script_root_resolver": helper_script_root_resolver,
    }


def run_scanner_cwd_historical_replay(fixture: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(fixture) if fixture is not None else load_scanner_cwd_fixture()
    helpers = list(payload["critical_helpers"])
    before = analyze_scanner_path_resolution(str(payload["before"]["excerpt"]), helpers)
    after = analyze_scanner_path_resolution(str(payload["after"]["excerpt"]), helpers)

    reproduced = (
        before["known_defect_detected"]
        and before["cwd_relative_helper_count"] >= len(helpers)
        and not before["config_script_root_fallback"]
        and not after["known_defect_detected"]
        and after["cwd_relative_helper_count"] == 0
        and after["config_script_root_fallback"]
        and after["helper_script_root_resolver"]
    )

    return {
        "mode": "HISTORICAL-REPLAY",
        "source": dict(payload["source"]),
        "incident_family": payload["incident"]["family"],
        "before": before,
        "after": after,
        "historical_replay_claim": bool(reproduced),
        "transfer_claim": False,
        "production_world_claim": False,
    }

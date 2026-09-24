#!/usr/bin/env python3
"""Versioned JSON handoff adapter for in_ai and MSA One / MSA Patcher."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

from lola_library import catalog

JOB_SCHEMA = "Lola-HandoffJob-1.0"
RESULT_SCHEMA = "Lola-HandoffResult-1.0"
ADAPTER_NAME = "lola-handoff"
ADAPTER_VERSION = "1.0"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_STRING = 4096
MAX_ITEMS = 64
SAFE_JOB_TYPES = {
    "coding",
    "office",
    "apk-creator",
    "development",
    "deep-dive",
    "security",
    "apk-analysis",
}
SAFE_OPTION_KEYS = {
    "resolveUrls",
    "liveMonitor",
    "captureAllCode",
    "copyPublicCerts",
    "noPersistEvents",
    "decompile",
    "keepDecompiled",
    "cleanup",
    "noOpen",
}
SECRET_CONFIG_KEYS = {"apiKey", "token", "secret", "password"}
SAFE_PROJECT_JOB_TYPES = {"coding", "development", "deep-dive", "security"}
SAFE_APK_JOB_TYPES = {"deep-dive", "security", "apk-analysis"}
KNOWN_PROJECT_OUTPUTS = (
    "target-manifest.json",
    "url-report.json",
    "semgrep-results.json",
    "semgrep-report.html",
    "scan-modes.json",
    "preflight-analysis.json",
    "code-analysis.json",
    "network-analysis.json",
    "scan-events.json",
)


class ManifestError(ValueError):
    """Raised when the handoff manifest is invalid or unsafe."""


def _trim(value: str, limit: int = MAX_STRING) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def default_result_path(manifest_path: Path) -> Path:
    if manifest_path.suffix:
        return manifest_path.with_suffix(".result.json")
    return manifest_path.parent / f"{manifest_path.name}.result.json"


def bounded_load_manifest(manifest_path: Path) -> tuple[dict[str, Any], str]:
    manifest_path = manifest_path.resolve()
    if not manifest_path.exists():
        raise ManifestError(f"Manifest does not exist: {manifest_path}")
    size = manifest_path.stat().st_size
    if size > MAX_MANIFEST_BYTES:
        raise ManifestError(
            f"Manifest exceeds {MAX_MANIFEST_BYTES} bytes: {manifest_path}"
        )
    raw = manifest_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Manifest is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("Manifest root must be a JSON object.")
    return data, raw


def _expect_string(
    field_name: str, value: Any, *, required: bool = True, max_len: int = MAX_STRING
) -> str | None:
    if value is None:
        if required:
            raise ManifestError(f"{field_name} is required.")
        return None
    if not isinstance(value, str):
        raise ManifestError(f"{field_name} must be a string.")
    if not value.strip():
        raise ManifestError(f"{field_name} must not be empty.")
    if len(value) > max_len:
        raise ManifestError(f"{field_name} exceeds {max_len} characters.")
    return value


def _resolve_local_path(
    value: str, base: Path, *, allow_parent_segments: bool
) -> Path:
    if "\x00" in value:
        raise ManifestError("Path values must not contain NUL characters.")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        if not allow_parent_segments and any(part == ".." for part in candidate.parts):
            raise ManifestError(
                "Relative output paths must stay inside the manifest directory."
            )
        candidate = (base / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def _validate_options(value: Any) -> dict[str, bool]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError("job.lola.options must be an object.")
    if len(value) > len(SAFE_OPTION_KEYS):
        raise ManifestError("job.lola.options contains too many entries.")
    out: dict[str, bool] = {}
    for key, entry in value.items():
        if key not in SAFE_OPTION_KEYS:
            raise ManifestError(f"Unsupported Lola option: {key}")
        if not isinstance(entry, bool):
            raise ManifestError(f"job.lola.options.{key} must be true or false.")
        out[key] = entry
    return out


def _validate_checks(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ManifestError("job.lola.checks must be an array.")
    if len(value) > MAX_ITEMS:
        raise ManifestError("job.lola.checks contains too many items.")
    allowed_checks = {x["id"] for x in catalog()["apkPlan"]}
    checks: list[str] = []
    for item in value:
        check = _expect_string("job.lola.checks[]", item, max_len=64)
        if check not in allowed_checks:
            raise ManifestError(f"Unsupported APK plan check: {check}")
        checks.append(check)
    return checks


def _validate_assistant_config(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError("assistantConfig must be an object when provided.")
    if len(value) > 4:
        raise ManifestError("assistantConfig contains too many entries.")
    out: dict[str, str] = {}
    for key, entry in value.items():
        if key in SECRET_CONFIG_KEYS:
            raise ManifestError(
                "assistantConfig must reference explicit user environment variables, not raw secrets."
            )
        if key not in {"provider", "baseUrl", "model", "apiKeyEnv"}:
            raise ManifestError(f"Unsupported assistantConfig field: {key}")
        out[key] = _expect_string(f"assistantConfig.{key}", entry, max_len=256) or ""
    return out


def validate_manifest(
    manifest: dict[str, Any], manifest_path: Path
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    schema = _expect_string("schema", manifest.get("schema"), max_len=64)
    if schema != JOB_SCHEMA:
        raise ManifestError(f"Unsupported manifest schema: {schema}")

    job = manifest.get("job")
    if not isinstance(job, dict):
        raise ManifestError("job must be an object.")

    manifest_base = manifest_path.resolve().parent
    job_id = _expect_string("job.id", job.get("id"), max_len=128) or ""
    job_type = _expect_string("job.type", job.get("type"), max_len=64) or ""
    if job_type not in SAFE_JOB_TYPES:
        raise ManifestError(f"Unsupported job.type: {job_type}")

    sender = manifest.get("sender") or {}
    if sender and not isinstance(sender, dict):
        raise ManifestError("sender must be an object when provided.")

    target = job.get("target")
    if not isinstance(target, dict):
        raise ManifestError("job.target must be an object.")
    target_value = _expect_string("job.target.path", target.get("path"))
    target_path = _resolve_local_path(
        target_value or "", manifest_base, allow_parent_segments=True
    )
    if not target_path.exists():
        raise ManifestError(f"Target path does not exist: {target_path}")

    lola_cfg = job.get("lola") or {}
    if lola_cfg and not isinstance(lola_cfg, dict):
        raise ManifestError("job.lola must be an object when provided.")
    requested_mode = _expect_string(
        "job.lola.mode", lola_cfg.get("mode"), required=False, max_len=64
    )
    checks = _validate_checks(lola_cfg.get("checks"))
    options = _validate_options(lola_cfg.get("options"))

    result_cfg = manifest.get("result") or {}
    if result_cfg and not isinstance(result_cfg, dict):
        raise ManifestError("result must be an object when provided.")
    requested_result = _expect_string(
        "result.path", result_cfg.get("path"), required=False
    )
    result_path = (
        _resolve_local_path(
            requested_result, manifest_base, allow_parent_segments=False
        )
        if requested_result
        else default_result_path(manifest_path)
    )

    research_brief = manifest.get("researchBrief") or {}
    if research_brief and not isinstance(research_brief, dict):
        raise ManifestError("researchBrief must be an object when provided.")
    if research_brief.get("path") is not None:
        _expect_string("researchBrief.path", research_brief.get("path"))
    if research_brief.get("format") is not None:
        _expect_string("researchBrief.format", research_brief.get("format"), max_len=64)

    assistant_config = _validate_assistant_config(manifest.get("assistantConfig"))

    job_notes = job.get("notes")
    if job_notes is not None:
        _expect_string("job.notes", job_notes)

    target_kind = (
        "apk"
        if target_path.is_file() and target_path.suffix.lower() == ".apk"
        else ("directory" if target_path.is_dir() else "file")
    )
    if job_type == "apk-creator":
        warnings.append(
            "Lola does not build, patch, or re-sign APKs through the handoff adapter."
        )
    if job_type == "office":
        warnings.append(
            "Office handoffs are accepted for provenance, but execution stays manual and local."
        )
    if assistant_config and assistant_config.get("provider") != "qwen-compatible":
        warnings.append(
            "assistantConfig is recorded for manual handoff only; Lola does not contact model providers."
        )

    return (
        {
            "schema": schema,
            "sender": sender,
            "job": {
                "id": job_id,
                "type": job_type,
                "targetPath": target_path,
                "targetKind": target_kind,
                "notes": job_notes or "",
                "mode": requested_mode,
                "checks": checks,
                "options": options,
            },
            "resultPath": result_path,
            "researchBrief": research_brief,
            "assistantConfig": assistant_config,
        },
        warnings,
    )


def _project_modes() -> set[str]:
    entries = {
        x["id"]
        for x in catalog()["commands"]
        if x.get("group") in {"Security", "Code", "Network", "Pre-scan"}
    }
    entries.update({"/360", "/deep-dive", "/deep-dive code", "/deep-dive network"})
    return entries


def _apk_modes() -> set[str]:
    return {
        x["id"]
        for x in catalog()["commands"]
        if x.get("group") == "APK" and x.get("id") != "/apktools"
    }


def _project_mode_for(job_type: str, requested_mode: str | None) -> str:
    mode = requested_mode or {
        "coding": "/deep-dive code",
        "development": "/360",
        "deep-dive": "/deep-dive",
        "security": "/360",
    }[job_type]
    if mode not in _project_modes():
        raise ManifestError(f"Unsupported project mode for handoff: {mode}")
    return mode


def _apk_mode_for(requested_mode: str | None) -> str:
    mode = requested_mode or "/apk360"
    if mode not in _apk_modes():
        raise ManifestError(f"Unsupported APK mode for handoff: {mode}")
    return mode


def _collect_existing_outputs(directory: Path) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for name in KNOWN_PROJECT_OUTPUTS:
        path = directory / name
        if path.exists():
            outputs[path.name] = str(path)
    return outputs


def _execute_project_job(
    job: dict[str, Any], artifact_dir: Path
) -> tuple[int, dict[str, str], list[str]]:
    from argparse import Namespace

    from lola import run_project

    options = job["options"]
    args = Namespace(
        mode=_project_mode_for(job["type"], job["mode"]),
        resolve_urls=options.get("resolveUrls", False),
        live_monitor=options.get("liveMonitor", False),
        capture_all_code=options.get("captureAllCode", False),
        copy_public_certs=options.get("copyPublicCerts", False),
        cleanup=options.get("cleanup", False),
        no_persist_events=options.get("noPersistEvents", False),
        no_open=options.get("noOpen", True),
    )
    previous = Path.cwd()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(artifact_dir)
    try:
        rc = run_project(args, job["targetPath"])
    finally:
        os.chdir(previous)
    return rc, _collect_existing_outputs(artifact_dir), []


def _execute_apk_job(
    job: dict[str, Any], artifact_dir: Path
) -> tuple[int, dict[str, str], list[str]]:
    from argparse import Namespace

    from lola import run_apk

    artifact_dir.mkdir(parents=True, exist_ok=True)
    args = Namespace(
        mode=_apk_mode_for(job["mode"]),
        checks=",".join(job["checks"]),
        decompile=job["options"].get("decompile", False),
        keep_decompiled=job["options"].get("keepDecompiled", False),
        apk_analysis=str(artifact_dir / "apk-analysis.json"),
        apk_report=str(artifact_dir / "apk-report.html"),
        cleanup=job["options"].get("cleanup", False),
        no_open=job["options"].get("noOpen", True),
    )
    rc = run_apk(args, job["targetPath"])
    outputs = {}
    for key, path in {
        "analysis": Path(args.apk_analysis),
        "report": Path(args.apk_report),
    }.items():
        if path.exists():
            outputs[key] = str(path)
    return rc, outputs, []


def _manual_only_result(message: str) -> tuple[int, dict[str, str], list[str]]:
    return 0, {}, [message]


def _execute_job(
    validated: dict[str, Any], artifact_dir: Path
) -> tuple[str, int, dict[str, str], list[str]]:
    job = validated["job"]
    target_kind = job["targetKind"]
    job_type = job["type"]

    if job_type == "apk-creator":
        rc, outputs, warnings = _manual_only_result(
            "APK creation or patching is unsupported; Lola only performs local analysis and reporting."
        )
        return "unsupported", rc, outputs, warnings
    if job_type == "office":
        rc, outputs, warnings = _manual_only_result(
            "Office jobs require explicit local use of lola_office_engine.py or lola_integration_brain.py."
        )
        return "unsupported", rc, outputs, warnings

    if target_kind == "apk":
        if job_type not in SAFE_APK_JOB_TYPES:
            rc, outputs, warnings = _manual_only_result(
                f"Job type '{job_type}' is not executable against APK targets."
            )
            return "unsupported", rc, outputs, warnings
        rc, outputs, warnings = _execute_apk_job(job, artifact_dir)
        return ("complete" if rc == 0 else "failed"), rc, outputs, warnings

    if job_type == "apk-analysis":
        rc, outputs, warnings = _manual_only_result(
            "APK analysis requires an .apk target file."
        )
        return "unsupported", rc, outputs, warnings

    if job_type not in SAFE_PROJECT_JOB_TYPES:
        rc, outputs, warnings = _manual_only_result(
            f"Job type '{job_type}' is accepted for provenance but not executable by Lola."
        )
        return "unsupported", rc, outputs, warnings

    rc, outputs, warnings = _execute_project_job(job, artifact_dir)
    return ("complete" if rc == 0 else "failed"), rc, outputs, warnings


def _result_template(
    *,
    manifest_path: Path,
    raw_manifest_sha256: str | None,
    validated: dict[str, Any] | None,
    initial_warnings: list[str],
) -> dict[str, Any]:
    target = (validated or {}).get("job", {})
    target_path = target.get("targetPath")
    target_kind = target.get("targetKind")
    provenance: dict[str, Any] = {
        "manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": raw_manifest_sha256 or "",
        },
        "adapter": {
            "name": ADAPTER_NAME,
            "version": ADAPTER_VERSION,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
    }
    if isinstance(target_path, Path):
        target_info = {
            "path": str(target_path),
            "kind": target_kind,
            "exists": target_path.exists(),
        }
        if target_path.is_file():
            target_info["size"] = target_path.stat().st_size
            target_info["sha256"] = _sha256_file(target_path)
        provenance["target"] = target_info
    return {
        "schema": RESULT_SCHEMA,
        "status": "failed",
        "job": {
            "id": target.get("id", ""),
            "type": target.get("type", ""),
        },
        "sender": (validated or {}).get("sender", {}),
        "warnings": list(initial_warnings),
        "researchBrief": (validated or {}).get("researchBrief", {}),
        "assistantConfig": (validated or {}).get("assistantConfig", {}),
        "provenance": provenance,
        "startedAt": _now_iso(),
        "finishedAt": None,
        "outputPaths": {},
        "notes": _trim(target.get("notes", "")),
    }


def write_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["resultPath"] = str(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def handoff_exit_code(result: dict[str, Any]) -> int:
    return 0 if result.get("status") == "complete" else 2


def execute_handoff_manifest(
    manifest_path: Path, result_path: Path | None = None
) -> dict[str, Any]:
    started = time.time()
    manifest_path = manifest_path.resolve()
    manifest_sha = _sha256_file(manifest_path) if manifest_path.exists() else None
    validated: dict[str, Any] | None = None
    initial_warnings: list[str] = []
    resolved_result = result_path.resolve() if result_path else default_result_path(manifest_path)
    result: dict[str, Any]

    try:
        raw_manifest, raw_text = bounded_load_manifest(manifest_path)
        manifest_sha = _sha256_text(raw_text)
        validated, initial_warnings = validate_manifest(raw_manifest, manifest_path)
        if result_path is None:
            resolved_result = Path(validated["resultPath"]).resolve()
        artifact_dir = resolved_result.parent / f"{validated['job']['id']}-artifacts"
        result = _result_template(
            manifest_path=manifest_path,
            raw_manifest_sha256=manifest_sha,
            validated=validated,
            initial_warnings=initial_warnings,
        )
        status, rc, outputs, execution_warnings = _execute_job(validated, artifact_dir)
        result["status"] = status
        result["commandStatus"] = rc
        result["warnings"].extend(execution_warnings)
        result["outputPaths"] = outputs
    except ManifestError as exc:
        result = _result_template(
            manifest_path=manifest_path,
            raw_manifest_sha256=manifest_sha,
            validated=validated,
            initial_warnings=initial_warnings,
        )
        result["status"] = "invalid-manifest"
        result["commandStatus"] = 2
        result["warnings"].append(str(exc))
    except SystemExit as exc:
        result = _result_template(
            manifest_path=manifest_path,
            raw_manifest_sha256=manifest_sha,
            validated=validated,
            initial_warnings=initial_warnings,
        )
        result["status"] = "failed"
        result["commandStatus"] = int(exc.code) if isinstance(exc.code, int) else 1
        result["warnings"].append(_trim(str(exc)))
    except Exception as exc:
        result = _result_template(
            manifest_path=manifest_path,
            raw_manifest_sha256=manifest_sha,
            validated=validated,
            initial_warnings=initial_warnings,
        )
        result["status"] = "failed"
        result["commandStatus"] = 1
        result["warnings"].append(f"Unexpected adapter failure: {_trim(str(exc))}")

    result["finishedAt"] = _now_iso()
    result["durationSeconds"] = round(time.time() - started, 3)
    write_result(resolved_result, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a versioned local Lola handoff manifest for in_ai / MSA One."
    )
    parser.add_argument("manifest", help="Path to Lola-HandoffJob-1.0 JSON manifest.")
    parser.add_argument(
        "--result",
        help="Optional output path for the Lola-HandoffResult-1.0 JSON artifact.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = execute_handoff_manifest(
        Path(args.manifest), Path(args.result) if args.result else None
    )
    print("HANDOFF STATUS :", result.get("status"))
    print("HANDOFF RESULT :", result.get("resultPath"))
    if result.get("warnings"):
        print("WARNINGS      :", len(result["warnings"]))
    return handoff_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())

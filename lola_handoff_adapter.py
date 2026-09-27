#!/usr/bin/env python3
"""Versioned local handoff adapter for MyAI and MSA One/MSA Patcher."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from lola_code_integration import compile_plan, extraction_plan, identify
from lola_library import catalog

ROOT = Path(__file__).resolve().parent
CONTRACT_VERSION = "1.0"
PROVIDER = "lola"
PLANNER_PROVIDER = "lola-planner"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_REQUEST_CHARS = 16 * 1024
MAX_RESULT_BYTES = 512 * 1024
MAX_FILES = 128
MAX_WARNINGS = 32
MAX_FINDINGS = 128
MAX_SECTIONS = 16
MAX_ARTIFACTS = 32

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_FAILED = 3
EXIT_UNSUPPORTED = 4
EXIT_PARTIAL = 5

EXECUTABLE_TASKS = {"security-scan", "deep-dive"}
PLANNING_TASKS = {"coding", "development"}
UNSUPPORTED_TASKS = {"office", "apk-creator"}
KNOWN_TASKS = EXECUTABLE_TASKS | PLANNING_TASKS | UNSUPPORTED_TASKS
SAFE_OPTION_FLAGS = {
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
SAFE_TARGETS = {"lola", "lola-local"}
SECRET_RE = re.compile(
    r"""(?ix)
    (
      (?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|secret|password)
      \s*[:=]\s*
    )
    ([^\s,'"}\]]+)
    """
)
HEX_SECRET_RE = re.compile(r"\b[a-f0-9]{32,}\b", re.I)


class HandoffError(ValueError):
    """Raised when a handoff manifest or execution request is invalid."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    handle = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            handle.update(chunk)
    return handle.hexdigest()


def _trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _redact_text(value: str) -> str:
    redacted = SECRET_RE.sub(r"\1<REDACTED>", value)
    return HEX_SECRET_RE.sub("<REDACTED>", redacted)


def _sanitize_text(value: Any, limit: int = 4096) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return _redact_text(_trim(text, limit))


def _json_string(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def _bounded_write_json(path: Path, payload: dict[str, Any]) -> None:
    text = _json_string(payload)
    if len(text.encode("utf-8")) > MAX_RESULT_BYTES:
        payload["warnings"] = list(payload.get("warnings", []))[: MAX_WARNINGS - 1]
        payload["warnings"].append(
            "Result was truncated to stay within Lola's export size limit."
        )
        payload["sections"] = [
            {
                "id": "truncated",
                "title": "Truncated result",
                "items": [
                    "Original result exceeded the maximum export size.",
                    "Inspect local artifact files for full raw outputs.",
                ],
            }
        ]
        payload["findings"] = []
        payload["artifacts"] = list(payload.get("artifacts", []))[:MAX_ARTIFACTS]
        text = _json_string(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _default_result_path(manifest_path: Path) -> Path:
    if manifest_path.suffix:
        return manifest_path.with_suffix(".result.json")
    return manifest_path.parent / f"{manifest_path.name}.result.json"


def _expect_string(
    field: str, value: Any, *, required: bool = True, max_len: int = 512
) -> str | None:
    if value is None:
        if required:
            raise HandoffError(EXIT_INVALID, f"{field} is required.")
        return None
    if not isinstance(value, str):
        raise HandoffError(EXIT_INVALID, f"{field} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise HandoffError(EXIT_INVALID, f"{field} must not be empty.")
    if len(stripped) > max_len:
        raise HandoffError(EXIT_INVALID, f"{field} exceeds {max_len} characters.")
    return stripped


def _expect_bool(field: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise HandoffError(EXIT_INVALID, f"{field} must be true or false.")
    return value


def _expect_object(field: str, value: Any, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise HandoffError(EXIT_INVALID, f"{field} is required.")
        return {}
    if not isinstance(value, dict):
        raise HandoffError(EXIT_INVALID, f"{field} must be an object.")
    return value


def _expect_list(field: str, value: Any, *, required: bool = True) -> list[Any]:
    if value is None:
        if required:
            raise HandoffError(EXIT_INVALID, f"{field} is required.")
        return []
    if not isinstance(value, list):
        raise HandoffError(EXIT_INVALID, f"{field} must be an array.")
    return value


def _resolve_base_path(root_value: str | None, manifest_path: Path) -> Path:
    if root_value is None:
        return manifest_path.parent.resolve()
    candidate = Path(root_value).expanduser()
    if not candidate.is_absolute():
        candidate = (manifest_path.parent / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def _resolve_relative_file(root: Path, relative_path: str) -> Path:
    if "\x00" in relative_path:
        raise HandoffError(EXIT_INVALID, "selectedFiles[].path must not contain NUL bytes.")
    rel = Path(relative_path)
    if rel.is_absolute():
        raise HandoffError(EXIT_INVALID, "selectedFiles[].path must be relative.")
    if any(part == ".." for part in rel.parts):
        raise HandoffError(EXIT_INVALID, "selectedFiles[].path must stay inside the project root.")
    return (root / rel).resolve()


def _resolve_result_path(value: str | None, manifest_path: Path) -> Path:
    if not value:
        return _default_result_path(manifest_path)
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    rel = Path(value)
    if any(part == ".." for part in rel.parts):
        raise HandoffError(EXIT_INVALID, "Result paths must stay inside the manifest directory.")
    return (manifest_path.parent / rel).resolve()


def _allowed_apk_checks() -> set[str]:
    return {entry["id"] for entry in catalog()["apkPlan"]}


def _validate_options(value: Any) -> dict[str, Any]:
    options = _expect_object("options", value, required=False)
    normalized: dict[str, Any] = {"flags": {}, "checks": [], "mode": None, "resultPath": None}
    if not options:
        return normalized
    if len(options) > len(SAFE_OPTION_FLAGS) + 3:
        raise HandoffError(EXIT_INVALID, "options contains too many entries.")
    for key, entry in options.items():
        if key == "mode":
            normalized["mode"] = _expect_string("options.mode", entry, max_len=64)
            continue
        if key == "resultPath":
            normalized["resultPath"] = _expect_string("options.resultPath", entry, max_len=512)
            continue
        if key == "checks":
            checks = _expect_list("options.checks", entry)
            if len(checks) > MAX_FILES:
                raise HandoffError(EXIT_INVALID, "options.checks contains too many entries.")
            allowed = _allowed_apk_checks()
            for item in checks:
                check = _expect_string("options.checks[]", item, max_len=64)
                if check not in allowed:
                    raise HandoffError(EXIT_INVALID, f"Unsupported APK check: {check}")
                normalized["checks"].append(check)
            continue
        if key not in SAFE_OPTION_FLAGS:
            raise HandoffError(EXIT_INVALID, f"Unsupported option: {key}")
        normalized["flags"][key] = _expect_bool(f"options.{key}", entry)
    return normalized


def _sanitize_project(project: dict[str, Any], manifest_path: Path) -> tuple[dict[str, Any], Path]:
    root_value = project.get("rootPath")
    root_path = _resolve_base_path(
        _expect_string("project.rootPath", root_value, required=False, max_len=1024),
        manifest_path,
    )
    metadata: dict[str, Any] = {}
    for key in ("id", "name", "description", "platform", "owner"):
        if key in project and project[key] is not None:
            metadata[key] = _sanitize_text(project[key], 512)
    metadata["rootPath"] = str(root_path)
    return metadata, root_path


def _validate_selected_files(value: Any, root_path: Path) -> list[dict[str, Any]]:
    items = _expect_list("selectedFiles", value)
    if len(items) > MAX_FILES:
        raise HandoffError(EXIT_INVALID, f"selectedFiles exceeds {MAX_FILES} entries.")
    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(items):
        row = _expect_object(f"selectedFiles[{index}]", entry)
        rel_path = _expect_string(f"selectedFiles[{index}].path", row.get("path"), max_len=1024)
        absolute_path = _resolve_relative_file(root_path, rel_path or "")
        size = row.get("size")
        if size is not None and (not isinstance(size, int) or size < 0):
            raise HandoffError(EXIT_INVALID, f"selectedFiles[{index}].size must be a non-negative integer.")
        sha256 = row.get("sha256")
        if sha256 is not None:
            sha256 = _expect_string(f"selectedFiles[{index}].sha256", sha256, max_len=64)
            if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
                raise HandoffError(EXIT_INVALID, f"selectedFiles[{index}].sha256 must be a 64-character hex digest.")
        normalized.append(
            {
                "path": rel_path,
                "size": size,
                "sha256": sha256.lower() if isinstance(sha256, str) else None,
                "exists": absolute_path.exists(),
                "absolutePath": absolute_path,
            }
        )
    return normalized


def _lola_version() -> str:
    try:
        output = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
        return output.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _project_mode(task_type: str, requested_mode: str | None) -> str:
    default_mode = "/deep-dive" if task_type == "deep-dive" else "/360"
    mode = requested_mode or default_mode
    if not mode.startswith("/"):
        mode = "/" + mode
    return mode


def _apk_mode(requested_mode: str | None) -> str:
    mode = requested_mode or "/apk360"
    if not mode.startswith("/"):
        mode = "/" + mode
    return mode if mode.startswith("/apk") else "/apk360"


def _execution_target(
    task_type: str, project_root: Path, selected_files: list[dict[str, Any]]
) -> tuple[Path, str]:
    apk_files = [
        item["absolutePath"]
        for item in selected_files
        if item["path"].lower().endswith(".apk")
    ]
    if apk_files:
        if len(apk_files) != 1:
            raise HandoffError(EXIT_INVALID, "APK jobs must reference exactly one .apk file.")
        target = apk_files[0]
    else:
        target = project_root
        if (
            len(selected_files) == 1
            and selected_files[0]["absolutePath"].exists()
            and selected_files[0]["absolutePath"].is_file()
        ):
            target = selected_files[0]["absolutePath"]
    if not target.exists():
        raise HandoffError(EXIT_INVALID, f"Execution target does not exist: {target}")
    target_kind = "apk" if target.is_file() and target.suffix.lower() == ".apk" else (
        "directory" if target.is_dir() else "file"
    )
    if task_type in EXECUTABLE_TASKS and target_kind == "apk":
        return target, target_kind
    if task_type in EXECUTABLE_TASKS | PLANNING_TASKS and target_kind in {"directory", "file"}:
        return target, target_kind
    return target, target_kind


def bounded_load_manifest(manifest_path: Path) -> tuple[dict[str, Any], bytes]:
    resolved = manifest_path.resolve()
    if not resolved.exists():
        raise HandoffError(EXIT_INVALID, f"Manifest does not exist: {resolved}")
    size = resolved.stat().st_size
    if size > MAX_MANIFEST_BYTES:
        raise HandoffError(EXIT_INVALID, f"Manifest exceeds {MAX_MANIFEST_BYTES} bytes.")
    raw = resolved.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HandoffError(EXIT_INVALID, f"Manifest is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise HandoffError(EXIT_INVALID, "Manifest root must be a JSON object.")
    return data, raw


def validate_manifest(manifest: dict[str, Any], manifest_path: Path) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    version = _expect_string("contractVersion", manifest.get("contractVersion"), max_len=16)
    if version != CONTRACT_VERSION:
        raise HandoffError(EXIT_INVALID, f"Unsupported contractVersion: {version}")
    job_id = _expect_string("jobId", manifest.get("jobId"), max_len=128) or ""
    source = _expect_string("source", manifest.get("source"), max_len=64) or ""
    target = _expect_string("target", manifest.get("target"), max_len=64) or ""
    task_type = _expect_string("taskType", manifest.get("taskType"), max_len=64) or ""
    if task_type not in KNOWN_TASKS:
        raise HandoffError(EXIT_INVALID, f"Unsupported taskType: {task_type}")
    request = _expect_string("request", manifest.get("request"), max_len=MAX_REQUEST_CHARS) or ""
    project = _expect_object("project", manifest.get("project"))
    project_meta, project_root = _sanitize_project(project, manifest_path)
    selected_files = _validate_selected_files(manifest.get("selectedFiles"), project_root)
    options = _validate_options(manifest.get("options"))
    authorization = _expect_object("authorization", manifest.get("authorization"))
    confirmed = _expect_bool("authorization.confirmed", authorization.get("confirmed"))
    scope = _expect_string("authorization.scope", authorization.get("scope"), max_len=256) or ""
    created_at = _expect_string("createdAt", manifest.get("createdAt"), max_len=64) or ""
    execution_target, execution_kind = _execution_target(task_type, project_root, selected_files)
    result_path = _resolve_result_path(
        options.get("resultPath"), manifest_path
    )

    if target.lower() not in SAFE_TARGETS:
        warnings.append("This local adapter expects target 'lola'; execution will be treated as unsupported.")
    if not confirmed:
        warnings.append("Authorization.confirmed is false; Lola will refuse to execute local analysis.")
    if task_type in UNSUPPORTED_TASKS:
        warnings.append(f"Task type '{task_type}' is planning-only or unsupported in Lola.")
    if task_type in EXECUTABLE_TASKS and execution_kind != "apk" and execution_target.suffix.lower() == ".apk":
        warnings.append("APK analysis uses existing local APK routes only.")

    return (
        {
            "contractVersion": version,
            "jobId": job_id,
            "source": source,
            "target": target,
            "taskType": task_type,
            "request": request,
            "project": project_meta,
            "projectRoot": project_root,
            "selectedFiles": selected_files,
            "options": options,
            "authorization": {"confirmed": confirmed, "scope": scope},
            "createdAt": created_at,
            "executionTarget": execution_target,
            "executionKind": execution_kind,
            "resultPath": result_path,
        },
        warnings[:MAX_WARNINGS],
    )


def validate_handoff_manifest(manifest_path: Path) -> tuple[dict[str, Any], int]:
    try:
        manifest, raw = bounded_load_manifest(manifest_path)
        validated, warnings = validate_manifest(manifest, manifest_path.resolve())
        payload = {
            "ok": True,
            "contractVersion": validated["contractVersion"],
            "jobId": validated["jobId"],
            "taskType": validated["taskType"],
            "executionTarget": str(validated["executionTarget"]),
            "executionKind": validated["executionKind"],
            "resultPath": str(validated["resultPath"]),
            "manifestSha256": _sha256_bytes(raw),
            "warnings": warnings,
            "createdAt": _now_iso(),
        }
        return payload, EXIT_OK
    except HandoffError as exc:
        return {
            "ok": False,
            "error": {"code": exc.code, "message": str(exc)},
            "createdAt": _now_iso(),
        }, exc.code


def _collect_project_outputs(directory: Path) -> dict[str, str]:
    known = (
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
    outputs: dict[str, str] = {}
    for name in known:
        path = directory / name
        if path.exists():
            outputs[name] = str(path.resolve())
    return outputs


def _artifact_metadata(label: str, path: Path) -> dict[str, Any]:
    artifact = {
        "type": label,
        "path": str(path.resolve()),
    }
    if path.exists() and path.is_file():
        artifact["size"] = path.stat().st_size
        artifact["sha256"] = _sha256_file(path)
    return artifact


def _execute_project_scan(validated: dict[str, Any], artifact_dir: Path) -> tuple[int, dict[str, str], list[str]]:
    from argparse import Namespace

    from lola import run_project

    flags = validated["options"]["flags"]
    args = Namespace(
        mode=_project_mode(validated["taskType"], validated["options"].get("mode")),
        resolve_urls=flags.get("resolveUrls", False),
        live_monitor=flags.get("liveMonitor", False),
        capture_all_code=flags.get("captureAllCode", False),
        copy_public_certs=flags.get("copyPublicCerts", False),
        cleanup=flags.get("cleanup", False),
        no_persist_events=flags.get("noPersistEvents", False),
        no_open=flags.get("noOpen", True),
    )
    previous = Path.cwd()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    try:
        import os

        os.chdir(artifact_dir)
        rc = run_project(args, validated["executionTarget"])
    except SystemExit as exc:
        rc = int(exc.code) if isinstance(exc.code, int) else EXIT_FAILED
        warnings.append(_sanitize_text(str(exc), 512))
    finally:
        import os

        os.chdir(previous)
    return rc, _collect_project_outputs(artifact_dir), warnings


def _execute_apk_scan(validated: dict[str, Any], artifact_dir: Path) -> tuple[int, dict[str, str], list[str]]:
    from argparse import Namespace

    from lola import run_apk

    flags = validated["options"]["flags"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    args = Namespace(
        mode=_apk_mode(validated["options"].get("mode")),
        checks=",".join(validated["options"].get("checks", [])),
        decompile=flags.get("decompile", False),
        keep_decompiled=flags.get("keepDecompiled", False),
        apk_analysis=str((artifact_dir / "apk-analysis.json").resolve()),
        apk_report=str((artifact_dir / "apk-report.html").resolve()),
        cleanup=flags.get("cleanup", False),
        no_open=flags.get("noOpen", True),
    )
    rc = run_apk(args, validated["executionTarget"])
    outputs: dict[str, str] = {}
    for label, path in {
        "apk-analysis.json": Path(args.apk_analysis),
        "apk-report.html": Path(args.apk_report),
    }.items():
        if path.exists():
            outputs[label] = str(path.resolve())
    return rc, outputs, []


def _planning_sections(validated: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    sections: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    file_rows = validated["selectedFiles"][:20]
    if not file_rows and validated["executionTarget"].exists():
        file_rows = [
            {
                "path": validated["executionTarget"].name,
                "absolutePath": validated["executionTarget"],
                "size": validated["executionTarget"].stat().st_size
                if validated["executionTarget"].is_file()
                else None,
                "sha256": _sha256_file(validated["executionTarget"])
                if validated["executionTarget"].is_file()
                else None,
            }
        ]
    for index, row in enumerate(file_rows):
        path = row["absolutePath"]
        if not path.exists() or not path.is_file():
            warnings.append(f"Planning skipped missing file: {row['path']}")
            continue
        ident = identify(path)
        compile_info = compile_plan(path)
        extract_info = extraction_plan(path)
        findings.append(
            {
                "id": f"plan-{index + 1}",
                "path": row["path"],
                "language": ident.get("language"),
                "compileSupported": compile_info.get("supported", False),
                "provider": PLANNER_PROVIDER,
            }
        )
        sections.append(
            {
                "id": f"file-{index + 1}",
                "title": row["path"],
                "items": [
                    {"identify": ident},
                    {"compilePlan": compile_info},
                    {"extractionPlan": extract_info},
                ],
            }
        )
    if not sections:
        sections.append(
            {
                "id": "planning",
                "title": "Planning only",
                "items": [
                    "No concrete file plans were generated.",
                    "Lola did not execute compilers or unknown scripts.",
                ],
            }
        )
    return sections[:MAX_SECTIONS], findings[:MAX_FINDINGS], warnings[:MAX_WARNINGS]


def _result_template(validated: dict[str, Any], manifest_path: Path, manifest_sha256: str) -> dict[str, Any]:
    target = validated["executionTarget"]
    tool_status = compile_plan(target) if target.is_file() else {"supported": False, "reason": "directory target"}
    provenance: dict[str, Any] = {
        "lolaVersion": _lola_version(),
        "adapter": "lola-handoff-adapter",
        "command": "",
        "manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": manifest_sha256,
        },
        "input": {
            "source": validated["source"],
            "target": validated["target"],
            "taskType": validated["taskType"],
            "project": validated["project"],
            "selectedFiles": [
                {
                    "path": item["path"],
                    "size": item["size"],
                    "sha256": item["sha256"],
                    "exists": item["exists"],
                }
                for item in validated["selectedFiles"]
            ],
        },
        "authorization": dict(validated["authorization"]),
        "timestamps": {"manifestCreatedAt": validated["createdAt"], "startedAt": _now_iso()},
        "toolStatus": {"executionKind": validated["executionKind"], "compilePlan": tool_status},
        "artifactPaths": [],
    }
    if target.exists():
        target_meta = {
            "path": str(target),
            "kind": validated["executionKind"],
            "exists": True,
        }
        if target.is_file():
            target_meta["size"] = target.stat().st_size
            target_meta["sha256"] = _sha256_file(target)
        provenance["input"]["executionTarget"] = target_meta
    return {
        "contractVersion": CONTRACT_VERSION,
        "jobId": validated["jobId"],
        "status": "failed",
        "provider": PROVIDER,
        "summary": "",
        "sections": [],
        "findings": [],
        "artifacts": [],
        "warnings": [],
        "provenance": provenance,
        "createdAt": _now_iso(),
    }


def _execute_validated_job(
    validated: dict[str, Any], artifact_dir: Path
) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], list[str], str]:
    if validated["target"].lower() not in SAFE_TARGETS:
        return (
            "unsupported",
            "Manifest target does not address the local Lola adapter.",
            [],
            [],
            ["Expected target 'lola' for local execution."],
            PLANNER_PROVIDER,
        )
    if not validated["authorization"]["confirmed"]:
        return (
            "unsupported",
            "Authorization confirmation is required before Lola will execute local analysis.",
            [],
            [],
            ["Set authorization.confirmed to true only for targets you own or are authorized to inspect."],
            PLANNER_PROVIDER,
        )
    if validated["taskType"] in UNSUPPORTED_TASKS:
        message = f"Task type '{validated['taskType']}' is not executable in Lola."
        return "unsupported", message, [], [], [message], PLANNER_PROVIDER
    if validated["taskType"] in PLANNING_TASKS:
        sections, findings, warnings = _planning_sections(validated)
        return (
            "partial",
            "Lola generated a safe local plan without pretending to complete the requested work.",
            sections,
            findings,
            warnings,
            PLANNER_PROVIDER,
        )

    if validated["executionKind"] == "apk":
        rc, outputs, warnings = _execute_apk_scan(validated, artifact_dir)
    else:
        rc, outputs, warnings = _execute_project_scan(validated, artifact_dir)

    artifacts = [
        _artifact_metadata(label, Path(path))
        for label, path in sorted(outputs.items())
    ]
    sections = [
        {
            "id": "execution",
            "title": "Executed local Lola analysis",
            "items": [
                f"Task type: {validated['taskType']}",
                f"Execution target: {validated['executionTarget']}",
                f"Artifacts generated: {len(artifacts)}",
            ],
        }
    ]
    if rc == 0 and artifacts:
        return "completed", "Lola completed the requested local analysis.", sections, [], warnings, PROVIDER
    if rc == 0:
        warnings.append("Lola completed without generating expected artifacts.")
        return "partial", "Lola finished but produced no export artifacts.", sections, [], warnings, PROVIDER

    if validated["taskType"] in EXECUTABLE_TASKS:
        plan_sections, plan_findings, plan_warnings = _planning_sections(validated)
        warnings.extend(plan_warnings)
        warnings.append("Lola returned a fallback safe local plan after analysis execution failed.")
        return (
            "partial" if plan_sections else "failed",
            "Lola could not complete the requested analysis and returned a safe local fallback plan.",
            sections + plan_sections,
            plan_findings,
            warnings,
            PLANNER_PROVIDER if plan_sections else PROVIDER,
        )
    return "failed", "Lola failed to complete the requested work.", sections, [], warnings, PROVIDER


def handoff_exit_code(result: dict[str, Any]) -> int:
    return {
        "completed": EXIT_OK,
        "failed": EXIT_FAILED,
        "unsupported": EXIT_UNSUPPORTED,
        "partial": EXIT_PARTIAL,
    }.get(result.get("status"), EXIT_FAILED)


def execute_handoff_manifest(manifest_path: Path, result_path: Path | None = None) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    started = time.time()
    try:
        manifest, raw = bounded_load_manifest(manifest_path)
        manifest_sha256 = _sha256_bytes(raw)
        validated, validation_warnings = validate_manifest(manifest, manifest_path)
    except HandoffError as exc:
        result = {
            "contractVersion": CONTRACT_VERSION,
            "jobId": "",
            "status": "failed",
            "provider": PROVIDER,
            "summary": _sanitize_text(str(exc), 512),
            "sections": [],
            "findings": [],
            "artifacts": [],
            "warnings": [_sanitize_text(str(exc), 512)],
            "provenance": {
                "lolaVersion": _lola_version(),
                "command": f"python lola.py --handoff-run {manifest_path}",
                "manifest": {"path": str(manifest_path), "sha256": ""},
                "timestamps": {"startedAt": _now_iso(), "finishedAt": _now_iso()},
            },
            "createdAt": _now_iso(),
            "error": {"code": exc.code, "message": str(exc)},
        }
        destination = result_path.resolve() if result_path else _default_result_path(manifest_path)
        _bounded_write_json(destination, result)
        result["resultPath"] = str(destination)
        return result

    destination = result_path.resolve() if result_path else validated["resultPath"]
    result = _result_template(validated, manifest_path, manifest_sha256)
    result["warnings"].extend(validation_warnings[:MAX_WARNINGS])
    result["provenance"]["command"] = f"python lola.py --handoff-run {manifest_path}"
    artifact_dir = destination.parent / f"{validated['jobId']}-artifacts"

    status, summary, sections, findings, warnings, provider = _execute_validated_job(
        validated, artifact_dir
    )
    result["status"] = status
    result["provider"] = provider
    result["summary"] = _sanitize_text(summary, 512)
    result["sections"] = sections[:MAX_SECTIONS]
    result["findings"] = findings[:MAX_FINDINGS]
    result["warnings"].extend(_sanitize_text(item, 512) for item in warnings[:MAX_WARNINGS])

    artifacts = []
    for path in artifact_dir.glob("*"):
        artifacts.append(_artifact_metadata(path.name, path))
    result["artifacts"] = artifacts[:MAX_ARTIFACTS]
    result["provenance"]["artifactPaths"] = [item["path"] for item in result["artifacts"]]
    result["provenance"]["timestamps"]["finishedAt"] = _now_iso()
    result["provenance"]["timestamps"]["durationSeconds"] = round(time.time() - started, 3)
    result["createdAt"] = _now_iso()
    _bounded_write_json(destination, result)
    result["resultPath"] = str(destination)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or run a local Lola handoff contract v1.0 manifest."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate a handoff manifest.")
    validate.add_argument("manifest", help="Path to a handoff manifest JSON file.")
    run = sub.add_parser("run", help="Execute a handoff manifest locally.")
    run.add_argument("manifest", help="Path to a handoff manifest JSON file.")
    run.add_argument("--result", help="Optional result JSON output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        payload, code = validate_handoff_manifest(Path(args.manifest))
        print(_json_string(payload))
        return code
    result = execute_handoff_manifest(
        Path(args.manifest),
        Path(args.result).resolve() if args.result else None,
    )
    print(_json_string(result))
    return handoff_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())

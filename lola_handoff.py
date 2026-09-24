#!/usr/bin/env python3
"""Safe local handoff adapter for MyAI/MSA job manifests."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from lola_library import catalog, list_targets
from lola_metatrader_bot import capabilities as mt_capabilities
from lola_metatrader_bot import compile_source as mt_compile_source
from lola_metatrader_bot import static_check as mt_static_check
from lola_toolchain import status as toolchain_status

CONTRACT_VERSION = "1.0"
HANDOFF_ROOT = Path(__file__).resolve().parent / ".lola-handoff"
MAX_REQUEST_CHARS = 4000
MAX_SELECTED_FILES = 64
MAX_SELECTED_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_SELECTED_BYTES = 16 * 1024 * 1024
MAX_SNIPPET_CHARS = 1200
MAX_OUTPUT_CHARS = 6000
SAFE_CHECK_TIMEOUT = 20
JOB_ID_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")
SHA256_RX = re.compile(r"^[0-9a-fA-F]{64}$")
WINDOWS_DRIVE_RX = re.compile(r"^[A-Za-z]:[\\/]")

SUPPORTED_COMMANDS = {
    "/deep-dive",
    "/autocomplete",
    "/progresswork",
    "/alldataai",
    "/allcodelibrary",
    "/buildoncloud",
    "/aimt4",
    "/aimt5",
    "/aiide",
    "/aipy",
    "/aicpp",
}
SUPPORTED_TASK_TYPES = SUPPORTED_COMMANDS | {
    "deep-dive",
    "autocomplete",
    "coding",
    "office",
    "apk-creator",
    "development",
    "security-scan",
}
AUTHORIZED_SCOPES = {
    "user-owned-or-authorized-project",
    "authorized-local-workspace",
    "authorized-project-files",
    "selected-paths-only",
}
EXIT_CODES = {
    "completed": 0,
    "partial": 0,
    "blocked": 3,
    "unsupported": 4,
    "failed": 1,
    "invalid": 2,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def redact_secret_text(text: str) -> str:
    redacted = text
    rules = [
        (re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,})"), "[REDACTED_GITHUB_TOKEN]"),
        (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "[REDACTED_AWS_ACCESS_KEY]"),
        (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED_PRIVATE_KEY]"),
        (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)\b\s*[:=]\s*([\"'])?([^\s,\"']+)"), r"\1=[REDACTED]"),
    ]
    for pattern, replacement in rules:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def bounded_text(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 32] + "\n...[truncated by Lola]..."


def normalize_command(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if not raw.startswith("/"):
        raw = "/" + raw
    raw = raw.replace("_", "-")
    aliases = {
        "/deepdive": "/deep-dive",
        "/deep-dive-main": "/deep-dive",
        "/progress-work": "/progresswork",
        "/all-data-ai": "/alldataai",
        "/all-code-library": "/allcodelibrary",
        "/build-on-cloud": "/buildoncloud",
        "/mt4": "/aimt4",
        "/mt5": "/aimt5",
        "/py": "/aipy",
        "/cpp": "/aicpp",
    }
    return aliases.get(raw, raw)


def safe_relative_path(value: str) -> str:
    candidate = (value or "").replace("\\", "/").strip()
    if not candidate:
        raise ValueError("path is required")
    if candidate.startswith("/") or WINDOWS_DRIVE_RX.match(candidate):
        raise ValueError("absolute paths are not allowed")
    pure = PurePosixPath(candidate)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError("path traversal is not allowed")
    normalized = pure.as_posix().lstrip("./")
    if not normalized or normalized.startswith("../"):
        raise ValueError("path traversal is not allowed")
    return normalized


def safe_join(root: Path, relative_path: str) -> Path:
    candidate = (root / safe_relative_path(relative_path)).resolve()
    root = root.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("path traversal is not allowed")
    return candidate


def default_workspace_root(manifest_path: Path | None) -> Path:
    if manifest_path:
        return manifest_path.resolve().parent
    return Path.cwd().resolve()


def error_packet(code: str, message: str, *, status: str = "failed", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    packet = {"status": status, "errorCode": code, "message": message}
    if extra:
        packet.update(extra)
    return packet


def job_dir(job_id: str) -> Path:
    safe_job = safe_relative_path(job_id)
    folder = HANDOFF_ROOT / safe_job
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_progress(
    job_id: str,
    command: str,
    status: str,
    phase: str,
    progress_percent: int,
    *,
    completed: list[str] | None = None,
    current: str = "",
    blocked: list[str] | None = None,
    tests: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    provider: str = "lola-local",
    requires_user_confirmation: bool = False,
) -> dict[str, Any]:
    payload = {
        "jobId": job_id,
        "command": command,
        "status": status,
        "phase": phase,
        "progressPercent": max(0, min(100, int(progress_percent))),
        "completed": completed or [],
        "current": current,
        "blocked": blocked or [],
        "tests": tests or [],
        "artifacts": artifacts or [],
        "provider": provider,
        "requiresUserConfirmation": bool(requires_user_confirmation),
        "updatedAt": now_iso(),
    }
    folder = job_dir(job_id)
    write_json(folder / "progress.json", payload)
    return payload


def result_base(job_id: str, command: str, status: str, summary: str, provider: str = "lola-local") -> dict[str, Any]:
    return {
        "contractVersion": CONTRACT_VERSION,
        "jobId": job_id,
        "command": command,
        "status": status,
        "provider": provider,
        "summary": summary,
        "findings": [],
        "artifacts": [],
        "warnings": [],
        "provenance": {
            "tool": "lola",
            "toolVersion": CONTRACT_VERSION,
            "createdAt": now_iso(),
            "hostPlatform": platform.system(),
            "python": sys.version.split()[0],
        },
    }


def add_artifact(result: dict[str, Any], path: Path, kind: str) -> None:
    if not path.exists():
        return
    entry = {"kind": kind, "path": str(path)}
    if path.is_file():
        entry["sha256"] = sha256_file(path)
        entry["size"] = path.stat().st_size
    result.setdefault("artifacts", []).append(entry)


def validate_manifest_data(
    data: dict[str, Any],
    *,
    workspace_root: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    normalized: dict[str, Any] = dict(data)

    if data.get("contractVersion") != CONTRACT_VERSION:
        errors.append(error_packet("LOLA_E_CONTRACT_VERSION", "contractVersion must be 1.0", status="invalid"))

    job_id = str(data.get("jobId") or "")
    if not JOB_ID_RX.fullmatch(job_id):
        errors.append(error_packet("LOLA_E_JOB_ID", "jobId must be 3-80 characters of [A-Za-z0-9._-]", status="invalid"))

    request_text = str(data.get("request") or "")
    if len(request_text) > MAX_REQUEST_CHARS:
        errors.append(error_packet("LOLA_E_REQUEST_BOUNDS", f"request exceeds {MAX_REQUEST_CHARS} characters", status="invalid"))

    task_type = str(data.get("taskType") or "")
    command = normalize_command(data.get("command") or task_type)
    if task_type not in SUPPORTED_TASK_TYPES and command not in SUPPORTED_COMMANDS:
        errors.append(error_packet("LOLA_E_TASK_TYPE", f"Unsupported taskType/command: {task_type or command or '<empty>'}", status="invalid"))
    normalized["command"] = command

    authorization = data.get("authorization") if isinstance(data.get("authorization"), dict) else {}
    if authorization.get("confirmed") is not True:
        errors.append(error_packet("LOLA_E_AUTH_CONFIRM", "authorization.confirmed must be true", status="invalid"))
    if authorization.get("scope") not in AUTHORIZED_SCOPES:
        errors.append(error_packet("LOLA_E_AUTH_SCOPE", "authorization.scope is not allowed", status="invalid"))

    selected = data.get("selectedFiles")
    if selected is None:
        selected = []
    if not isinstance(selected, list):
        errors.append(error_packet("LOLA_E_SELECTED_FILES", "selectedFiles must be an array", status="invalid"))
        selected = []
    if len(selected) > MAX_SELECTED_FILES:
        errors.append(error_packet("LOLA_E_SELECTED_FILES_BOUNDS", f"selectedFiles exceeds {MAX_SELECTED_FILES} entries", status="invalid"))

    total_size = 0
    normalized_selected: list[dict[str, Any]] = []
    for item in selected:
        if not isinstance(item, dict):
            errors.append(error_packet("LOLA_E_SELECTED_FILES", "each selectedFiles entry must be an object", status="invalid"))
            continue
        rel_path = str(item.get("path") or "")
        try:
            normalized_path = safe_relative_path(rel_path)
            absolute = safe_join(workspace_root, normalized_path)
        except ValueError as exc:
            errors.append(error_packet("LOLA_E_PATH", f"{rel_path or '<empty>'}: {exc}", status="invalid"))
            continue
        if not absolute.exists() or not absolute.is_file():
            errors.append(error_packet("LOLA_E_PATH_MISSING", f"selected file not found: {normalized_path}", status="invalid"))
            continue

        actual_size = absolute.stat().st_size
        if actual_size > MAX_SELECTED_FILE_BYTES:
            errors.append(error_packet("LOLA_E_FILE_BOUNDS", f"{normalized_path} exceeds {MAX_SELECTED_FILE_BYTES} bytes", status="invalid"))
            continue

        declared_size = item.get("size")
        if not isinstance(declared_size, int) or declared_size < 0:
            errors.append(error_packet("LOLA_E_SELECTED_METADATA", f"{normalized_path} must include a non-negative integer size", status="invalid"))
            continue
        if declared_size != actual_size:
            errors.append(error_packet("LOLA_E_SELECTED_METADATA", f"{normalized_path} size metadata mismatch", status="invalid"))
            continue

        declared_hash = item.get("sha256")
        actual_hash = sha256_file(absolute)
        if declared_hash:
            if not isinstance(declared_hash, str) or not SHA256_RX.fullmatch(declared_hash):
                errors.append(error_packet("LOLA_E_SELECTED_METADATA", f"{normalized_path} sha256 metadata is invalid", status="invalid"))
                continue
            if declared_hash.lower() != actual_hash:
                errors.append(error_packet("LOLA_E_SELECTED_METADATA", f"{normalized_path} sha256 metadata mismatch", status="invalid"))
                continue

        total_size += actual_size
        normalized_selected.append(
            {
                "path": normalized_path,
                "absolutePath": str(absolute),
                "size": actual_size,
                "sha256": actual_hash,
                "language": detect_language(absolute),
            }
        )

    if total_size > MAX_TOTAL_SELECTED_BYTES:
        errors.append(error_packet("LOLA_E_TOTAL_BOUNDS", f"selectedFiles total exceeds {MAX_TOTAL_SELECTED_BYTES} bytes", status="invalid"))

    normalized["workspaceRoot"] = str(workspace_root)
    normalized["selectedFiles"] = normalized_selected
    normalized["manifestPath"] = str(manifest_path) if manifest_path else None
    normalized["project"] = data.get("project") if isinstance(data.get("project"), dict) else {}
    normalized["options"] = data.get("options") if isinstance(data.get("options"), dict) else {}

    return {
        "ok": not errors,
        "errors": errors,
        "normalized": normalized,
    }


def load_manifest(path: Path, workspace_root: Path | None = None) -> dict[str, Any]:
    manifest_path = path.resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = workspace_root.resolve() if workspace_root else default_workspace_root(manifest_path)
    return validate_manifest_data(data, workspace_root=root, manifest_path=manifest_path)


def safe_subprocess(cmd: list[str], timeout: int = SAFE_CHECK_TIMEOUT) -> dict[str, Any]:
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        output = bounded_text(redact_secret_text((run.stdout or "") + ("\n" if run.stdout and run.stderr else "") + (run.stderr or "")))
        return {
            "attempted": True,
            "command": cmd,
            "returncode": run.returncode,
            "timedOut": False,
            "output": output,
            "ok": run.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        raw = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
        return {
            "attempted": True,
            "command": cmd,
            "returncode": None,
            "timedOut": True,
            "output": bounded_text(redact_secret_text(raw)),
            "ok": False,
        }
    except OSError as exc:
        return {
            "attempted": False,
            "command": cmd,
            "returncode": None,
            "timedOut": False,
            "output": str(exc),
            "ok": False,
        }


def detect_language(path: Path) -> str | None:
    ext = path.suffix.lower()
    mapping = {
        ".py": "python",
        ".c": "c",
        ".cc": "cpp",
        ".cpp": "cpp",
        ".cxx": "cpp",
        ".h": "cpp-header",
        ".hpp": "cpp-header",
        ".js": "nodejs",
        ".mjs": "nodejs",
        ".cjs": "nodejs",
        ".vbs": "vbscript",
        ".wsf": "vbscript",
        ".mq4": "mql4",
        ".mq5": "mql5",
    }
    return mapping.get(ext)


def summarize_python(path: Path, run_safe_checks: bool) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(source)
    result = {
        "language": "python",
        "path": str(path),
        "imports": sorted({node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names})[:64],
        "functions": sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)),
        "classes": sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef)),
        "compilePlan": {"command": [sys.executable, "-m", "py_compile", str(path)], "tool": sys.executable},
        "toolAvailability": {"python": sys.executable},
        "safeCheck": {"attempted": False},
    }
    if run_safe_checks:
        result["safeCheck"] = safe_subprocess([sys.executable, "-m", "py_compile", str(path)])
    return result


def summarize_cpp(path: Path, run_safe_checks: bool) -> dict[str, Any]:
    compiler = shutil.which("g++") or shutil.which("clang++") or shutil.which("c++")
    includes: list[str] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = re.match(r'\s*#\s*include\s*[<"]([^">]+)[">]', line)
        if match:
            includes.append(match.group(1))
    result = {
        "language": "cpp",
        "path": str(path),
        "includes": includes[:128],
        "buildFiles": [name for name in ("CMakeLists.txt", "Makefile") if (path.parent / name).exists()],
        "compilePlan": {
            "commands": [
                [compiler or "g++", "-fsyntax-only", str(path)],
                [compiler or "g++", str(path), "-o", "<output>"],
            ],
            "tool": compiler,
        },
        "toolAvailability": {
            "g++": shutil.which("g++"),
            "clang++": shutil.which("clang++"),
            "cl": shutil.which("cl"),
        },
        "safeCheck": {"attempted": False},
    }
    if run_safe_checks and compiler and path.suffix.lower() in {".c", ".cc", ".cpp", ".cxx"}:
        result["safeCheck"] = safe_subprocess([compiler, "-fsyntax-only", str(path)])
    elif run_safe_checks:
        result["safeCheck"] = {"attempted": False, "reason": "safe syntax checks run only for C/C++ source files"}
    return result


def summarize_node(path: Path, run_safe_checks: bool) -> dict[str, Any]:
    package_json = path.parent / "package.json"
    lockfiles = [name for name in ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml") if (path.parent / name).exists()]
    scripts: dict[str, Any] = {}
    dependencies: dict[str, Any] = {}
    if package_json.exists():
        try:
            pkg = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {}) if isinstance(pkg.get("scripts"), dict) else {}
            dependencies = pkg.get("dependencies", {}) if isinstance(pkg.get("dependencies"), dict) else {}
        except Exception:
            scripts = {"_parseError": True}
    result = {
        "language": "nodejs",
        "path": str(path),
        "packageJson": str(package_json) if package_json.exists() else None,
        "lockfiles": lockfiles,
        "scripts": scripts,
        "dependencyCount": len(dependencies),
        "compilePlan": {"command": ["node", "--check", str(path)], "tool": shutil.which("node")},
        "toolAvailability": {"node": shutil.which("node"), "npm": shutil.which("npm")},
        "safeCheck": {"attempted": False},
    }
    if run_safe_checks and shutil.which("node"):
        result["safeCheck"] = safe_subprocess([shutil.which("node") or "node", "--check", str(path)])
    return result


def summarize_vbscript(path: Path, run_safe_checks: bool) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    com_objects = sorted(set(re.findall(r'CreateObject\(\s*"([^"]+)"', text, re.I)))[:64]
    usage = {
        "filesystem": bool(re.search(r"FileSystemObject|OpenTextFile|CreateTextFile|DeleteFile|DeleteFolder", text, re.I)),
        "process": bool(re.search(r"WScript\.Shell|Run\(|Exec\(", text, re.I)),
        "network": bool(re.search(r"XMLHTTP|ServerXMLHTTP|WinHttpRequest|ADODB\.Stream", text, re.I)),
    }
    is_windows = os.name == "nt"
    cscript = shutil.which("cscript") if is_windows else None
    result = {
        "language": "vbscript",
        "path": str(path),
        "windowsOnly": True,
        "supported": is_windows and bool(cscript),
        "comObjects": com_objects,
        "usage": usage,
        "compilePlan": {
            "command": [cscript or "cscript", "//nologo", str(path)],
            "note": "Runtime/syntax checks are Windows-only and require explicit safeChecks.",
        },
        "toolAvailability": {"cscript": cscript},
        "safeCheck": {"attempted": False},
    }
    if not is_windows:
        result["unsupportedReason"] = "VBScript runtime checks are Windows-only."
    elif run_safe_checks and cscript:
        result["safeCheck"] = safe_subprocess([cscript, "//nologo", str(path)])
    return result


def summarize_mql(path: Path, target: str, options: dict[str, Any]) -> dict[str, Any]:
    static = mt_static_check(path)
    caps = mt_capabilities()
    result = {
        "language": target,
        "path": str(path),
        "static": static,
        "toolAvailability": {"metaeditor": caps.get("metaeditor")},
        "compilePlan": {
            "supported": bool(caps.get("metaeditor")),
            "command": [caps.get("metaeditor") or "MetaEditor", "/compile:<selected-file>"],
            "note": "MQL4/MQL5 is analysis/compile-plan only unless an explicit configured MetaEditor tool exists and compile is requested.",
        },
        "safeCheck": {"attempted": False},
    }
    if options.get("compile") is True and caps.get("metaeditor"):
        result["safeCheck"] = mt_compile_source(path, editor=caps["metaeditor"], timeout=SAFE_CHECK_TIMEOUT)
    return result


def analyze_selected_languages(selected_files: list[dict[str, Any]], options: dict[str, Any], command: str) -> list[dict[str, Any]]:
    run_safe_checks = options.get("safeChecks") is True
    results: list[dict[str, Any]] = []
    for item in selected_files:
        path = Path(item["absolutePath"])
        language = item.get("language")
        try:
            if language == "python":
                results.append(summarize_python(path, run_safe_checks))
            elif language == "cpp" or language == "cpp-header":
                results.append(summarize_cpp(path, run_safe_checks and command == "/aicpp"))
            elif language == "nodejs":
                results.append(summarize_node(path, run_safe_checks))
            elif language == "vbscript":
                results.append(summarize_vbscript(path, run_safe_checks))
            elif language == "mql4":
                results.append(summarize_mql(path, "mql4", options))
            elif language == "mql5":
                results.append(summarize_mql(path, "mql5", options))
        except SyntaxError as exc:
            results.append({"language": language, "path": str(path), "safeCheck": {"attempted": False}, "error": f"syntax parse failed: {exc}"})
        except Exception as exc:
            results.append({"language": language, "path": str(path), "safeCheck": {"attempted": False}, "error": str(exc)})
    return results


def handler_deep_dive(manifest: dict[str, Any], folder: Path) -> dict[str, Any]:
    selected = manifest["selectedFiles"]
    write_progress(manifest["jobId"], manifest["command"], "running", "planning", 40, completed=["validated"], current="Creating local deep-dive plan")
    language_details = analyze_selected_languages(selected, manifest["options"], manifest["command"])
    result = result_base(manifest["jobId"], manifest["command"], "completed", "Generated a local deep-dive plan for authorized selected files.")
    result["findings"] = [
        {
            "type": "plan",
            "provider": "lola-local",
            "workspaceRoot": manifest["workspaceRoot"],
            "selectedFileCount": len(selected),
            "supportedCommands": sorted(SUPPORTED_COMMANDS),
            "languageDetails": language_details,
            "limitations": [
                "Lola remains a local desktop companion.",
                "Unsupported roles are reported explicitly instead of being simulated.",
                "No automatic cloud upload, APK patching, credential harvesting, stealth, DRM bypass, or destructive log deletion is performed.",
            ],
        }
    ]
    if not selected:
        result["warnings"].append("No selected files were provided; this is a planning-only deep dive.")
    add_artifact(result, folder / "progress.json", "progress")
    write_progress(manifest["jobId"], manifest["command"], "completed", "complete", 100, completed=["validated", "planned"], current="Deep-dive plan complete", artifacts=result["artifacts"])
    return result


def handler_autocomplete(manifest: dict[str, Any], folder: Path) -> dict[str, Any]:
    write_progress(manifest["jobId"], manifest["command"], "running", "planning", 50, completed=["validated"], current="Preparing autocomplete planning result")
    language_details = analyze_selected_languages(manifest["selectedFiles"], manifest["options"], manifest["command"])
    result = result_base(manifest["jobId"], manifest["command"], "partial", "Prepared local autocomplete context planning only.")
    result["warnings"].append("Lola does not act as a remote editor completion service; autocomplete is planning/context only.")
    result["findings"] = [
        {
            "type": "autocomplete-plan",
            "provider": "lola-local",
            "status": "planning-only",
            "selectedFiles": [{"path": item["path"], "language": item["language"]} for item in manifest["selectedFiles"]],
            "languageDetails": language_details,
            "unsupportedStates": ["live editor completion execution", "background remote coding"],
        }
    ]
    add_artifact(result, folder / "progress.json", "progress")
    write_progress(manifest["jobId"], manifest["command"], "completed", "complete", 100, completed=["validated", "planned"], current="Autocomplete plan complete", artifacts=result["artifacts"])
    return result


def handler_progresswork(manifest: dict[str, Any], folder: Path) -> dict[str, Any]:
    progress = write_progress(
        manifest["jobId"],
        manifest["command"],
        "running",
        "tracking",
        65,
        completed=["validated", "authorized", "selected-files-bounded"],
        current="Tracking local handoff progress",
        blocked=[],
        tests=[],
    )
    result = result_base(manifest["jobId"], manifest["command"], "completed", "Created a structured progress snapshot.")
    result["findings"] = [{"type": "progress", "snapshot": progress}]
    add_artifact(result, folder / "progress.json", "progress")
    write_progress(manifest["jobId"], manifest["command"], "completed", "complete", 100, completed=progress["completed"] + ["tracked"], current="Progress snapshot complete", artifacts=result["artifacts"])
    return result


def handler_alldataai(manifest: dict[str, Any], folder: Path) -> dict[str, Any]:
    selected = manifest["selectedFiles"]
    write_progress(manifest["jobId"], manifest["command"], "running", "indexing", 45, completed=["validated"], current="Indexing authorized selected files only")
    snippets = []
    total_bytes = 0
    for item in selected:
        path = Path(item["absolutePath"])
        total_bytes += item["size"]
        preview = ""
        try:
            preview = bounded_text(redact_secret_text(path.read_text(encoding="utf-8-sig", errors="replace")), MAX_SNIPPET_CHARS)
        except Exception:
            preview = "[binary-or-unreadable]"
        snippets.append(
            {
                "path": item["path"],
                "language": item["language"],
                "size": item["size"],
                "sha256": item["sha256"],
                "preview": preview,
            }
        )
    evidence_path = folder / "authorized-index.json"
    evidence = {"selectedFileCount": len(selected), "totalBytes": total_bytes, "files": snippets}
    write_json(evidence_path, evidence)
    result = result_base(manifest["jobId"], manifest["command"], "completed", "Built a bounded local index for authorized selected files.")
    result["findings"] = [
        {
            "type": "authorized-index",
            "selectedFileCount": len(selected),
            "totalBytes": total_bytes,
            "limits": {
                "maxSelectedFiles": MAX_SELECTED_FILES,
                "maxSelectedFileBytes": MAX_SELECTED_FILE_BYTES,
                "maxTotalSelectedBytes": MAX_TOTAL_SELECTED_BYTES,
            },
            "scope": "selected paths only",
        }
    ]
    result["warnings"].append("Lola did not scan the whole device; only explicit authorized selected files were processed.")
    add_artifact(result, folder / "progress.json", "progress")
    add_artifact(result, evidence_path, "authorized-index")
    write_progress(manifest["jobId"], manifest["command"], "completed", "complete", 100, completed=["validated", "indexed"], current="Authorized index complete", artifacts=result["artifacts"])
    return result


def handler_allcodelibrary(manifest: dict[str, Any], folder: Path) -> dict[str, Any]:
    write_progress(manifest["jobId"], manifest["command"], "running", "catalog", 50, completed=["validated"], current="Reading local catalog metadata")
    library = catalog()
    payload = {
        "localOnly": True,
        "commandCount": len(library.get("commands", [])),
        "functionCount": len(library.get("functions", [])),
        "targetCount": len(list_targets()),
        "storage": library.get("storage", {}),
    }
    metadata_path = folder / "catalog-metadata.json"
    write_json(metadata_path, payload)
    result = result_base(manifest["jobId"], manifest["command"], "completed", "Returned local Lola catalog metadata only.")
    result["findings"] = [{"type": "catalog", **payload}]
    result["warnings"].append("No remote code collection was performed; /allcodelibrary is local metadata only.")
    add_artifact(result, folder / "progress.json", "progress")
    add_artifact(result, metadata_path, "catalog-metadata")
    write_progress(manifest["jobId"], manifest["command"], "completed", "complete", 100, completed=["validated", "cataloged"], current="Catalog metadata complete", artifacts=result["artifacts"])
    return result


def handler_buildoncloud(manifest: dict[str, Any], folder: Path) -> dict[str, Any]:
    write_progress(
        manifest["jobId"],
        manifest["command"],
        "blocked",
        "preview",
        60,
        completed=["validated"],
        current="Prepared preview only; waiting for explicit user confirmation",
        blocked=["explicit user confirmation required before any workflow trigger"],
        requires_user_confirmation=True,
    )
    workflow_dir = Path(manifest["workspaceRoot"]) / ".github" / "workflows"
    workflows = []
    if workflow_dir.exists():
        for file in sorted(workflow_dir.glob("*.y*ml")):
            workflows.append({"path": str(file.relative_to(Path(manifest["workspaceRoot"]))), "name": file.stem})
    preview_path = folder / "cloud-build-preview.json"
    write_json(preview_path, {"workflows": workflows, "triggered": False, "credentialsUsed": False})
    result = result_base(manifest["jobId"], manifest["command"], "blocked", "Prepared a cloud-build preview; no workflow was triggered.")
    result["warnings"].extend(
        [
            "Explicit user confirmation is required before any workflow trigger.",
            "No hidden uploads or credentials were used.",
        ]
    )
    result["findings"] = [{"type": "cloud-build-preview", "workflows": workflows, "triggered": False, "requiresUserConfirmation": True}]
    add_artifact(result, folder / "progress.json", "progress")
    add_artifact(result, preview_path, "cloud-build-preview")
    return result


def handler_aiide(manifest: dict[str, Any], folder: Path) -> dict[str, Any]:
    write_progress(manifest["jobId"], manifest["command"], "running", "planning", 55, completed=["validated"], current="Preparing local IDE workspace diagnostics")
    files = [{"path": item["path"], "language": item["language"], "size": item["size"]} for item in manifest["selectedFiles"]]
    status = toolchain_status(Path(manifest["workspaceRoot"]))
    result = result_base(manifest["jobId"], manifest["command"], "completed", "Prepared a local workspace and diagnostics plan.")
    result["findings"] = [
        {
            "type": "workspace-plan",
            "workspaceRoot": manifest["workspaceRoot"],
            "selectedFiles": files,
            "toolchain": status,
            "boundaries": ["no arbitrary code execution", "no remote shell", "local planning and diagnostics only"],
        }
    ]
    add_artifact(result, folder / "progress.json", "progress")
    write_progress(manifest["jobId"], manifest["command"], "completed", "complete", 100, completed=["validated", "planned"], current="AI IDE plan complete", artifacts=result["artifacts"])
    return result


def handler_language(manifest: dict[str, Any], folder: Path, command: str, expected_languages: set[str]) -> dict[str, Any]:
    write_progress(manifest["jobId"], command, "running", "analysis", 55, completed=["validated"], current=f"Analyzing {command} selected files")
    details = [item for item in analyze_selected_languages(manifest["selectedFiles"], manifest["options"], command) if item.get("language") in expected_languages]
    status = "completed" if details else "unsupported"
    summary = f"Prepared local {command} analysis and compile planning." if details else f"No matching files were available for {command}."
    result = result_base(manifest["jobId"], command, status, summary)
    result["findings"] = [{"type": "language-analysis", "command": command, "details": details}]
    if status == "unsupported":
        result["warnings"].append(f"{command} requires matching authorized source files.")
    add_artifact(result, folder / "progress.json", "progress")
    write_progress(manifest["jobId"], command, "completed", "complete", 100, completed=["validated", "analyzed"], current=f"{command} analysis complete", artifacts=result["artifacts"])
    return result


HANDLERS = {
    "/deep-dive": handler_deep_dive,
    "/autocomplete": handler_autocomplete,
    "/progresswork": handler_progresswork,
    "/alldataai": handler_alldataai,
    "/allcodelibrary": handler_allcodelibrary,
    "/buildoncloud": handler_buildoncloud,
    "/aiide": handler_aiide,
}


def run_manifest(path: Path, *, workspace_root: Path | None = None) -> tuple[dict[str, Any], int]:
    loaded = load_manifest(path, workspace_root=workspace_root)
    if not loaded["ok"]:
        payload = {
            "contractVersion": CONTRACT_VERSION,
            "status": "failed",
            "errorCode": "LOLA_E_MANIFEST",
            "errors": loaded["errors"],
            "validatedAt": now_iso(),
        }
        return payload, EXIT_CODES["invalid"]

    manifest = loaded["normalized"]
    folder = job_dir(manifest["jobId"])
    write_json(folder / "manifest.json", {k: v for k, v in manifest.items() if k != "selectedFiles"} | {"selectedFiles": [{k: item[k] for k in ("path", "size", "sha256", "language")} for item in manifest["selectedFiles"]]})
    write_progress(manifest["jobId"], manifest["command"], "running", "validation", 15, completed=["manifest-loaded"], current="Manifest validated and authorized")

    command = manifest["command"]
    if command in HANDLERS:
        result = HANDLERS[command](manifest, folder)
    elif command == "/aipy":
        result = handler_language(manifest, folder, command, {"python"})
    elif command == "/aicpp":
        result = handler_language(manifest, folder, command, {"cpp", "cpp-header"})
    elif command == "/aimt4":
        result = handler_language(manifest, folder, command, {"mql4"})
    elif command == "/aimt5":
        result = handler_language(manifest, folder, command, {"mql5"})
    else:
        result = result_base(manifest["jobId"], command, "unsupported", f"{command} is not implemented for local execution.")
        result["warnings"].append("Unsupported commands are reported explicitly.")

    add_artifact(result, folder / "manifest.json", "manifest")
    add_artifact(result, folder / "progress.json", "progress")
    result_path = folder / "result.json"
    write_json(result_path, result)
    return result, EXIT_CODES.get(result["status"], 1)


def validate_manifest_cli(path: Path, *, workspace_root: Path | None = None) -> tuple[dict[str, Any], int]:
    loaded = load_manifest(path, workspace_root=workspace_root)
    payload = {
        "contractVersion": CONTRACT_VERSION,
        "validatedAt": now_iso(),
        "ok": loaded["ok"],
        "errors": loaded["errors"],
    }
    if loaded["ok"]:
        normalized = loaded["normalized"]
        payload["jobId"] = normalized["jobId"]
        payload["command"] = normalized["command"]
        payload["selectedFiles"] = [{k: item[k] for k in ("path", "size", "sha256", "language")} for item in normalized["selectedFiles"]]
    return payload, 0 if loaded["ok"] else EXIT_CODES["invalid"]


def handoff_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lola handoff", description="Lola MyAI/MSA handoff utilities")
    sub = parser.add_subparsers(dest="action", required=True)

    p_validate = sub.add_parser("validate", help="Validate a handoff manifest")
    p_validate.add_argument("manifest")
    p_validate.add_argument("--workspace-root", default="")

    p_run = sub.add_parser("run", help="Validate and run a handoff manifest")
    p_run.add_argument("manifest")
    p_run.add_argument("--workspace-root", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = handoff_parser()
    args = parser.parse_args(argv)
    workspace_root = Path(args.workspace_root).resolve() if args.workspace_root else None
    manifest = Path(args.manifest)
    if args.action == "validate":
        payload, code = validate_manifest_cli(manifest, workspace_root=workspace_root)
    else:
        payload, code = run_manifest(manifest, workspace_root=workspace_root)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

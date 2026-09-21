#!/usr/bin/env python3
"""Lola managed toolchain.

Keeps tool definitions in Git while third-party binaries live under .lola-tools/.
Downloads only from pinned official release/distribution sources declared in toolchain.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "toolchain.json"
CACHE = ROOT / ".lola-tools"
META = CACHE / "installed.json"
UA = "Lola-Toolchain/1.0"


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def tools_by_id() -> dict[str, dict[str, Any]]:
    return {x["id"]: x for x in load_manifest().get("tools", [])}


def host_platform() -> str:
    if "com.termux" in os.environ.get("PREFIX", "") or "termux" in os.environ.get("PREFIX", "").lower():
        return "termux"
    s = platform.system().lower()
    if s.startswith("win"): return "windows"
    if s == "darwin": return "darwin"
    return "linux"


def ensure_dirs():
    CACHE.mkdir(parents=True, exist_ok=True)
    if not META.exists():
        META.write_text(json.dumps({"version": 1, "tools": {}}, indent=2), encoding="utf-8")


def load_meta() -> dict[str, Any]:
    ensure_dirs()
    try:
        return json.loads(META.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "tools": {}}


def save_meta(data: dict[str, Any]):
    ensure_dirs()
    META.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def request_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def request_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8").strip()


def download(url: str, dest: Path):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r, dest.open("wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def safe_extract_zip(src: Path, dest: Path):
    dest = dest.resolve()
    with zipfile.ZipFile(src) as z:
        for member in z.infolist():
            out = (dest / member.filename).resolve()
            if not out.is_relative_to(dest):
                raise RuntimeError(f"Unsafe archive path: {member.filename}")
        z.extractall(dest)
    for p in dest.rglob("*"):
        if p.is_file() and (p.suffix == "" or p.name.endswith(".sh")):
            try:
                p.chmod(p.stat().st_mode | stat.S_IXUSR)
            except Exception:
                pass


def resolve_release_asset(tool: dict[str, Any]) -> tuple[str, str]:
    repo = tool["repository"]
    tag = tool["tag"]
    release = request_json(f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    rx = re.compile(tool["assetRegex"])
    matches = [a for a in release.get("assets", []) if rx.search(a.get("name", ""))]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one matching asset for {tool['id']}, found {len(matches)}")
    a = matches[0]
    return a["browser_download_url"], a["name"]


def expected_checksum(tool: dict[str, Any]) -> str:
    if tool.get("sha256"):
        return tool["sha256"].lower()
    if tool.get("checksumUrl"):
        text = request_text(tool["checksumUrl"])
        m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
        if not m:
            raise RuntimeError("Could not parse SHA-256 checksum")
        return m.group(1).lower()
    raise RuntimeError(f"No checksum source declared for {tool['id']}")


def managed_dir(tool_id: str) -> Path:
    return CACHE / tool_id


def find_managed_entry(tool: dict[str, Any]) -> Path | None:
    base = managed_dir(tool["id"])
    if not base.exists():
        return None
    if tool["id"] == "apktool":
        p = base / f"apktool_{tool['version']}.jar"
        return p if p.exists() else None
    if tool["id"] == "gradle":
        p = base / f"gradle-{tool['version']}"
        return p if p.exists() else None
    if tool["id"] == "ghidra":
        dirs = sorted([p for p in base.iterdir() if p.is_dir() and p.name.startswith(f"ghidra_{tool['version']}_")])
        return dirs[0] if dirs else None
    return base if base.exists() else None


def system_command(tool: dict[str, Any]) -> str | None:
    for name in tool.get("systemCommands", []):
        found = shutil.which(name)
        if found:
            return found
    return None


def hermes_project_path(project: Path | None) -> str | None:
    if not project:
        return None
    project = project.resolve()
    tool = tools_by_id().get("hermes", {})
    for rel in tool.get("candidates", []):
        p = project / rel
        if p.exists():
            return str(p)
    return None


def java_major() -> int | None:
    java = shutil.which("java")
    if not java:
        return None
    try:
        p = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=10)
        raw = (p.stderr or p.stdout)
        m = re.search(r'version\s+"(\d+)', raw)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def status(project: Path | None = None) -> dict[str, Any]:
    ensure_dirs()
    host = host_platform()
    meta = load_meta()
    out = []
    for tool in load_manifest().get("tools", []):
        tid = tool["id"]
        managed = find_managed_entry(tool)
        system = system_command(tool)
        project_path = hermes_project_path(project) if tid == "hermes" else None
        supported = host in tool.get("platforms", [])
        state = "missing"
        path = ""
        source = ""
        if project_path:
            state, path, source = "ready", project_path, "project"
        elif managed:
            state, path, source = "ready", str(managed), "managed"
        elif system:
            state, path, source = "ready", system, "system"
        elif not supported:
            state = "unsupported"
        elif tool.get("kind") == "project-detect":
            state = "project-required"
        elif tool.get("kind") == "system-detect":
            state = "external-required"

        min_java = tool.get("minimumJava")
        java_ok = True
        jv = None
        if "java" in tool.get("requires", []) or min_java:
            jv = java_major()
            java_ok = bool(jv and (not min_java or jv >= int(min_java)))
            if state == "ready" and not java_ok:
                state = "dependency-missing"

        out.append({
            "id": tid,
            "label": tool["label"],
            "version": tool.get("version", ""),
            "kind": tool.get("kind", ""),
            "state": state,
            "path": path,
            "source": source,
            "supported": supported,
            "host": host,
            "java": jv,
            "javaOk": java_ok,
            "minimumJava": min_java,
            "purpose": tool.get("purpose", ""),
            "managedInstall": tool.get("kind") in {"direct", "github-release-asset"} and supported,
            "metadata": meta.get("tools", {}).get(tid, {}),
        })
    return {"host": host, "root": str(CACHE), "tools": out}


def install(tool_id: str) -> dict[str, Any]:
    tools = tools_by_id()
    if tool_id not in tools:
        raise RuntimeError("Unknown tool")
    tool = tools[tool_id]
    if tool.get("kind") not in {"direct", "github-release-asset"}:
        raise RuntimeError(f"{tool['label']} is detect-only/project-aware and is not auto-downloaded by Lola.")
    if host_platform() not in tool.get("platforms", []):
        raise RuntimeError(f"{tool['label']} is not managed for this platform.")

    if "java" in tool.get("requires", []) and not shutil.which("java"):
        raise RuntimeError("Java is required before installing/using this tool.")
    if tool.get("minimumJava"):
        jv = java_major()
        if not jv or jv < int(tool["minimumJava"]):
            raise RuntimeError(f"{tool['label']} requires JDK {tool['minimumJava']} or newer.")

    ensure_dirs()
    base = managed_dir(tool_id)
    tmp_root = Path(tempfile.mkdtemp(prefix=f"lola_{tool_id}_", dir=str(CACHE)))
    try:
        if tool["kind"] == "github-release-asset":
            url, name = resolve_release_asset(tool)
        else:
            url = tool["url"]
            name = url.rstrip("/").split("/")[-1]
        archive = tmp_root / name
        download(url, archive)
        expected = expected_checksum(tool)
        actual = sha256_file(archive)
        if actual.lower() != expected:
            raise RuntimeError(f"Checksum mismatch for {tool_id}: expected {expected}, got {actual}")

        if base.exists():
            shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True, exist_ok=True)

        if tool.get("archive") == "zip":
            safe_extract_zip(archive, base)
        else:
            shutil.copy2(archive, base / name)

        meta = load_meta()
        meta.setdefault("tools", {})[tool_id] = {
            "version": tool.get("version"),
            "sha256": actual,
            "sourceUrl": url,
            "installedPath": str(base),
        }
        save_meta(meta)
        entry = find_managed_entry(tool)
        return {"ok": True, "tool": tool_id, "path": str(entry or base), "sha256": actual}
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def remove(tool_id: str) -> dict[str, Any]:
    base = managed_dir(tool_id)
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    meta = load_meta()
    meta.get("tools", {}).pop(tool_id, None)
    save_meta(meta)
    return {"ok": True, "tool": tool_id}


def command_for(tool_id: str) -> list[str] | None:
    tool = tools_by_id().get(tool_id)
    if not tool:
        return None
    managed = find_managed_entry(tool)
    if tool_id == "apktool" and managed:
        return [shutil.which("java") or "java", "-jar", str(managed)]
    if tool_id == "gradle" and managed:
        p = managed / "bin" / ("gradle.bat" if os.name == "nt" else "gradle")
        return [str(p)]
    if tool_id == "ghidra" and managed:
        p = managed / ("ghidraRun.bat" if os.name == "nt" else "ghidraRun")
        return [str(p)] if p.exists() else None
    system = system_command(tool)
    return [system] if system else None


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="action", required=True)
    p_status = sub.add_parser("status")
    p_status.add_argument("--project", default="")
    p_install = sub.add_parser("install")
    p_install.add_argument("tool")
    p_remove = sub.add_parser("remove")
    p_remove.add_argument("tool")
    p_path = sub.add_parser("path")
    p_path.add_argument("tool")
    args = ap.parse_args()

    if args.action == "status":
        project = Path(args.project) if args.project else None
        print(json.dumps(status(project), indent=2))
    elif args.action == "install":
        print(json.dumps(install(args.tool), indent=2))
    elif args.action == "remove":
        print(json.dumps(remove(args.tool), indent=2))
    elif args.action == "path":
        cmd = command_for(args.tool)
        print(json.dumps({"tool": args.tool, "command": cmd}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

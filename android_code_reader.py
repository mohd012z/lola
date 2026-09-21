#!/usr/bin/env python3
"""Build/search a redacted Android APK code-reader library."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any

MAX_TEXT_ENTRY = 512 * 1024
MAX_RESOURCE_ITEMS = 1200
MAX_DEX_STRINGS_PER_DEX = 2500
MAX_SOURCE_FILES = 2500
MAX_SOURCE_BYTES = 512 * 1024
MAX_SOURCE_PREVIEW = 24000
PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{6,}")
SECRET_ASSIGN_RE = re.compile(
    r"""(?ix)\b(?P<n>[A-Za-z_][A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|credential)[A-Za-z0-9_.-]*)\s*[:=]\s*(?P<q>["'])(?P<v>[^"'\r\n]{1,1000})(?P=q)"""
)
PROVIDER_TOKEN_RE = re.compile(r"(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]{0,50000}?-----END [A-Z0-9 ]*PRIVATE KEY-----")
CLASS_RE = re.compile(r"(?m)^\s*(?:public\s+|private\s+|protected\s+|internal\s+|abstract\s+|final\s+)*(?:class|interface|enum|object)\s+([A-Za-z_$][\w$]*)")
METHOD_RE = re.compile(r"(?m)^\s*(?:public|private|protected|internal|static|final|synchronized|native|abstract|suspend|override|\s)+[\w<>,?.\[\]$]+\s+([A-Za-z_$][\w$]*)\s*\(")
ANDROID_REF_RE = re.compile(r"(?i)\b(Activity|Service|BroadcastReceiver|ContentProvider|Intent|WebView|Context|SharedPreferences|RoomDatabase|SQLiteDatabase|Retrofit|OkHttpClient|WorkManager|Firebase|LocationManager|BiometricPrompt|KeyStore)\b")

TEXT_EXTS = {
    ".xml",".json",".txt",".html",".htm",".js",".css",".properties",".ini",".cfg",
    ".conf",".yaml",".yml",".md",".csv",".m3u8",".mpd",".smali",".java",".kt",
    ".gradle",".kts",".pro"
}
SOURCE_EXTS = {".java",".kt",".smali",".xml",".json",".js",".html",".properties",".gradle",".kts",".pro"}

def mask(v: str) -> str:
    if not v or len(v) <= 4:
        return "<redacted>"
    return v[:2] + "*" * min(max(len(v)-4,4),16) + v[-2:] + f" ({len(v)} chars)"

def redact(text: str) -> str:
    text = PRIVATE_KEY_RE.sub("<PRIVATE_KEY_REDACTED>", text)
    text = PROVIDER_TOKEN_RE.sub(lambda m: mask(m.group(0)), text)
    return SECRET_ASSIGN_RE.sub(
        lambda m: f'{m.group("n")}={m.group("q")}{mask(m.group("v"))}{m.group("q")}',
        text,
    )

def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default

def preview(text: str, limit: int = MAX_SOURCE_PREVIEW) -> str:
    return redact(text[:limit])

def build_reader(apk: Path, analysis_path: Path, source_dir: Path | None, output: Path) -> dict[str, Any]:
    analysis = read_json(analysis_path, {})
    resources: list[dict[str, Any]] = []
    dex_strings: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []

    if apk.exists() and zipfile.is_zipfile(apk):
        with zipfile.ZipFile(apk, "r") as z:
            for zi in z.infolist():
                p = zi.filename
                ext = Path(p).suffix.lower()
                if ext in TEXT_EXTS and zi.file_size and zi.file_size <= MAX_TEXT_ENTRY and len(resources) < MAX_RESOURCE_ITEMS:
                    try:
                        text = z.read(zi).decode("utf-8", "ignore")
                    except Exception:
                        text = ""
                    if text.strip():
                        resources.append({
                            "path": p,
                            "extension": ext or "[none]",
                            "bytes": zi.file_size,
                            "preview": preview(text, 18000),
                        })
                if re.fullmatch(r"classes(?:\d+)?\.dex", Path(p).name):
                    try:
                        data = z.read(zi)
                    except Exception:
                        continue
                    count = 0
                    for m in PRINTABLE_RE.finditer(data):
                        s = m.group(0).decode("utf-8", "ignore")
                        if not s:
                            continue
                        dex_strings.append({
                            "dex": p,
                            "offset": m.start(),
                            "value": redact(s[:900]),
                        })
                        count += 1
                        if count >= MAX_DEX_STRINGS_PER_DEX:
                            break

    if source_dir and source_dir.exists() and source_dir.is_dir():
        for p in source_dir.rglob("*"):
            if len(source_files) >= MAX_SOURCE_FILES:
                break
            if not p.is_file() or p.suffix.lower() not in SOURCE_EXTS:
                continue
            try:
                size = p.stat().st_size
                if size > MAX_SOURCE_BYTES:
                    source_files.append({
                        "path": str(p.relative_to(source_dir)),
                        "extension": p.suffix.lower(),
                        "bytes": size,
                        "preview": "",
                        "truncated": True,
                        "classes": [],
                        "methods": [],
                        "androidRefs": [],
                    })
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            classes = CLASS_RE.findall(text)[:80]
            methods = METHOD_RE.findall(text)[:160]
            refs = sorted(set(ANDROID_REF_RE.findall(text)))[:80]
            source_files.append({
                "path": str(p.relative_to(source_dir)),
                "extension": p.suffix.lower(),
                "bytes": size,
                "lines": text.count("\n") + 1,
                "preview": preview(text),
                "truncated": len(text) > MAX_SOURCE_PREVIEW,
                "classes": classes,
                "methods": methods,
                "androidRefs": refs,
            })

    sections = {
        "manifest": analysis.get("manifest", {}),
        "permissions": analysis.get("permissions", {}),
        "components": analysis.get("components", {}),
        "urls": analysis.get("urls", {}),
        "api": analysis.get("api", {}),
        "keys": analysis.get("keys", {}),
        "certs": analysis.get("certs", {}),
        "native": analysis.get("native", {}),
        "webview": analysis.get("webview", {}),
        "crypto": analysis.get("crypto", {}),
        "risk": analysis.get("risk", {}),
        "files": analysis.get("files", {}),
    }
    summary = {
        "apk": str(apk),
        "package": (analysis.get("summary") or {}).get("package", ""),
        "sha256": (analysis.get("summary") or {}).get("sha256", ""),
        "resourcePreviews": len(resources),
        "dexStrings": len(dex_strings),
        "sourceFiles": len(source_files),
        "sourceClasses": sum(len(x.get("classes", [])) for x in source_files),
        "sourceMethods": sum(len(x.get("methods", [])) for x in source_files),
        "jadxSourceAvailable": bool(source_dir and source_dir.exists()),
        "redacted": True,
    }
    out = {
        "version": 1,
        "summary": summary,
        "sections": sections,
        "resources": resources,
        "dexStrings": dex_strings,
        "sourceFiles": source_files,
        "readerViews": [
            "overview","manifest","permissions","components","source","resources","dex",
            "urls","api","keys","certs","native","webview","crypto","risk","files"
        ],
        "note": "Source/resource/DEX previews are bounded and secret-like values are redacted.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out

def search_reader(data: dict[str, Any], query: str, limit: int = 200) -> list[dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return []
    results: list[dict[str, Any]] = []

    def add(kind: str, title: str, location: str, text: str):
        if len(results) >= limit:
            return
        hay = f"{title}\n{location}\n{text}".lower()
        if q in hay:
            results.append({
                "kind": kind,
                "title": title,
                "location": location,
                "preview": text[:1800],
            })

    for x in data.get("sourceFiles", []):
        add("source", x.get("path",""), x.get("extension",""), x.get("preview",""))
    for x in data.get("resources", []):
        add("resource", x.get("path",""), x.get("extension",""), x.get("preview",""))
    for x in data.get("dexStrings", []):
        add("dex", x.get("value","")[:120], f'{x.get("dex","")} @ {x.get("offset","")}', x.get("value",""))

    for section_name in ("urls","api","keys","webview","crypto","risk","components","permissions","native","certs"):
        sec = (data.get("sections") or {}).get(section_name, {})
        items = sec.get("items", []) if isinstance(sec, dict) else []
        if isinstance(items, list):
            for idx, x in enumerate(items):
                add(section_name, section_name, str(idx), json.dumps(x, ensure_ascii=False))

    return results

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("apk")
    ap.add_argument("--analysis", default="apk-analysis.json")
    ap.add_argument("--source", default=".lola-apk/decompiled")
    ap.add_argument("--output", default="android-code-reader.json")
    args = ap.parse_args()

    apk = Path(args.apk).resolve()
    analysis = Path(args.analysis).resolve()
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    data = build_reader(apk, analysis, source if source.exists() else None, output)
    print(f"Android code reader written: {output}")
    print(json.dumps(data["summary"], indent=2))

if __name__ == "__main__":
    main()

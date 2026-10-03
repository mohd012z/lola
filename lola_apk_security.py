#!/usr/bin/env python3
"""Security/provenance integration helpers for APK analysis.

This module is intentionally side-effect free: it derives bounded provenance
metadata for an APK and selected child entries without changing analyzer output
or granting authority to artifact content.
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Any

from lola_analyzer_adapter import secure_artifact

MAX_PROVENANCE_ENTRIES = 512
MAX_HASH_ENTRY_BYTES = 8 * 1024 * 1024


def _id_part(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]


def collect_apk_security(
    apk_path: str | Path,
    *,
    project_id: str = "lola-apk-analysis",
    max_entries: int = MAX_PROVENANCE_ENTRIES,
) -> dict[str, Any]:
    apk = Path(apk_path).resolve()
    raw = apk.read_bytes()
    root = secure_artifact(
        artifact_id=f"apk:{hashlib.sha256(raw).hexdigest()[:24]}",
        project_id=project_id,
        source_type="APK",
        source_id=str(apk),
        payload=raw,
    )
    children: list[dict[str, Any]] = []
    skipped_large = 0
    truncated = False
    with zipfile.ZipFile(apk, "r") as archive:
        for info in archive.infolist():
            if len(children) >= max_entries:
                truncated = True
                break
            if info.is_dir():
                continue
            if info.file_size > MAX_HASH_ENTRY_BYTES:
                skipped_large += 1
                continue
            try:
                payload = archive.read(info)
            except Exception:
                continue
            source_type = "DEX" if Path(info.filename).name.startswith("classes") and info.filename.endswith(".dex") else "APK_ENTRY"
            child = secure_artifact(
                artifact_id=f"apk-entry:{_id_part(info.filename)}:{hashlib.sha256(payload).hexdigest()[:16]}",
                project_id=project_id,
                source_type=source_type,
                source_id=info.filename,
                payload=payload,
                parent=root.artifact,
                transformation="zip-entry-extract",
            )
            metadata = child.metadata()
            metadata.update({"bytes": info.file_size, "crc": f"{info.CRC:08x}"})
            children.append(metadata)
    return {
        "root": root.metadata(),
        "children": children,
        "bounded": True,
        "maxEntries": max_entries,
        "truncated": truncated,
        "skippedLargeEntries": skipped_large,
    }

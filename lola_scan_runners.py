#!/usr/bin/env python3
"""Scan runners shared by the CLI (lola.py) and the handoff adapter.

Extracted from lola.py so lola_handoff_adapter no longer imports the CLI
launcher (breaks the lola <-> lola_handoff_adapter import cycle).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from lola_library import register_target, set_plan, complete_scan, catalog

ROOT = Path(__file__).resolve().parent


def run(cmd: list[str]) -> int:
    print("\nLOLA MASTER")
    print("Command:", " ".join(f'"{x}"' if " " in x else x for x in cmd))
    print()
    return subprocess.call(cmd)


def normalize_mode(mode: str | None, is_apk: bool) -> str:
    if not mode:
        return "/apk360" if is_apk else "/360"
    if not mode.startswith("/"):
        mode = "/" + mode
    if is_apk and not mode.startswith("/apk"):
        return "/apk360"
    return mode


def run_apk(args: argparse.Namespace, target: Path) -> int:
    analyzer = ROOT / "analyze-apk.py"
    report_builder = ROOT / "build-apk-report.py"

    if not analyzer.exists():
        raise SystemExit(f"Missing APK analyzer: {analyzer}")
    if not report_builder.exists():
        raise SystemExit(f"Missing APK report builder: {report_builder}")

    mode = normalize_mode(args.mode, True)
    allowed_checks={x["id"] for x in catalog()["apkPlan"]}
    checks=[x.strip() for x in (args.checks or "").split(",") if x.strip() in allowed_checks]
    if not checks:
        checks=[x["id"] for x in catalog()["apkPlan"] if x.get("default")]
    if args.decompile and "decompile" not in checks:
        checks.append("decompile")
    target_record=register_target(target,target.name)
    if "store_target" in checks:
        set_plan(target_record["id"],checks,mode,{
            "decompile":args.decompile,"keepDecompiled":args.keep_decompiled,"cleanup":args.cleanup
        })
    analysis = Path(args.apk_analysis).resolve()
    html_report = Path(args.apk_report).resolve()

    cmd = [
        sys.executable,
        str(analyzer),
        str(target),
        "--output",
        str(analysis),
        "--checks",
        ",".join(checks),
    ]
    if args.decompile:
        cmd.append("--decompile")
    if args.keep_decompiled:
        cmd.append("--keep-extracted")

    rc = run(cmd)
    if rc != 0:
        return rc

    rc = run(
        [
            sys.executable,
            str(report_builder),
            "--input",
            str(analysis),
            "--output",
            str(html_report),
            "--mode",
            mode,
        ]
    )
    if rc != 0:
        return rc

    print("APK ANALYSIS:", analysis)
    print("APK VISUAL  :", html_report)
    try:
        analysis_data=json.loads(analysis.read_text(encoding="utf-8-sig"))
    except Exception:
        analysis_data={}
    if "store_target" in checks:
        complete_scan(
            target_record["id"],"complete",mode,checks,analysis_data,
            {"analysis":str(analysis),"report":str(html_report)}
        )

    if not args.no_open:
        try:
            import webbrowser
            webbrowser.open(html_report.as_uri())
        except Exception as exc:
            print("Could not open report automatically:", exc)

    if args.cleanup:
        decompiled = ROOT / ".lola-apk" / "decompiled"
        if decompiled.exists():
            shutil.rmtree(decompiled, ignore_errors=True)
            print("CLEANUP     :", decompiled)

    return 0


def find_powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")


def run_project(args: argparse.Namespace, target: Path) -> int:
    ps = find_powershell()
    scanner = ROOT / "scan-security.ps1"

    if not scanner.exists():
        raise SystemExit(f"Missing project scanner: {scanner}")
    if not ps:
        raise SystemExit(
            "Project/folder scanning currently uses scan-security.ps1. "
            "Install PowerShell 7 (pwsh) or run Lola on Windows."
        )

    mode = normalize_mode(args.mode, False)

    cmd = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(scanner),
        str(target),
        "-Mode",
        mode,
    ]

    if args.resolve_urls:
        cmd.append("-ResolveUrls")
    if args.live_monitor:
        cmd.append("-LiveMonitor")
    if args.capture_all_code:
        cmd.append("-CaptureAllCode")
    if args.copy_public_certs:
        cmd.append("-CopyPublicCerts")
    if args.cleanup:
        cmd.append("-CleanupLolaTemp")
    if args.no_persist_events:
        cmd.append("-NoPersistEvents")
    if args.no_open:
        cmd.append("-NoOpen")

    return run(cmd)

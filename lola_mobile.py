#!/usr/bin/env python3
"""
Lola Mobile - Android-friendly local web UI.

Run in Termux:
    python lola_mobile.py

Then open:
    http://127.0.0.1:8766
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from lola_library import catalog, register_target, set_plan, complete_scan, list_targets, load_target, archive_artifacts, artifact_paths, remove_generated_code
from android_code_reader import build_reader, search_reader
from frida_library import catalog as frida_catalog

ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / ".lola-mobile" / "uploads"
STATE_DIR = ROOT / ".lola-mobile"
ANALYZER = ROOT / "analyze-apk.py"
REPORTER = ROOT / "build-apk-report.py"
RUNTIME_MONITOR = ROOT / "apk_runtime_monitor.py"
RUNTIME_ANALYSIS = ROOT / "runtime-analysis.json"
RUNTIME_EVENTS = ROOT / "runtime-events.jsonl"
FRIDA_RUNNER = ROOT / "frida_runtime.py"
FRIDA_ANALYSIS = ROOT / "frida-analysis.json"
FRIDA_EVENTS = ROOT / "frida-events.jsonl"

HOST = "127.0.0.1"
PORT = 8766
MAX_UPLOAD = 2 * 1024 * 1024 * 1024  # 2 GB hard safety cap

STATE = {
    "status": "idle",
    "stage": "ready",
    "target": "",
    "targetId": "",
    "checks": [],
    "mode": "/apk360",
    "progress": 0,
    "message": "Ready",
    "started": None,
    "finished": None,
    "exitCode": None,
    "log": [],
    "report": "",
    "analysis": "",
    "reader": "",
    "tools": {},
    "runtime": {"status":"idle","package":"","message":"Ready","started":None,"finished":None,"exitCode":None},
    "frida": {"status":"idle","package":"","mode":"gadget","message":"Ready","started":None,"finished":None,"exitCode":None},
}
STATE_LOCK = threading.Lock()
PROCESS: subprocess.Popen | None = None
RUNTIME_PROCESS: subprocess.Popen | None = None
RUNTIME_LOCK = threading.Lock()
RUNTIME_STATE = {"status":"idle","package":"","message":"Ready","started":None,"finished":None,"exitCode":None}
FRIDA_PROCESS: subprocess.Popen | None = None
FRIDA_LOCK = threading.Lock()
FRIDA_STATE = {"status":"idle","package":"","mode":"gadget","message":"Ready","started":None,"finished":None,"exitCode":None}

APK_MODES = [
    ["/apk360","APK 360","Complete APK overview"],
    ["/apkmanifest","Manifest","Package, SDK and manifest"],
    ["/apkpermissions","Permissions","Declared Android permissions"],
    ["/apkcomponents","Components","Activities, services, receivers, providers"],
    ["/apkurls","URLs","Recovered endpoints"],
    ["/apkapi","API","API/auth/media endpoint references"],
    ["/apkkeys","Keys","Redacted key/token references"],
    ["/apkcerts","Certificates","Signing/certificate evidence"],
    ["/apknative","Native .SO","ABI and native libraries"],
    ["/apkwebview","WebView","WebView/JS bridge references"],
    ["/apkcrypto","Crypto","Cipher/hash/KDF/key-store references"],
    ["/apkfiles","Files","APK ZIP inventory"],
    ["/apkcode","Code / JADX","Optional decompilation status"],
    ["/apkrisk","Risk Review","Security review findings"],
    ["/apktools","Tools","Available local analyzers"],
]

def log(msg: str):
    with STATE_LOCK:
        stamp = time.strftime("%H:%M:%S")
        STATE["log"].append(f"[{stamp}] {msg}")
        STATE["log"] = STATE["log"][-1500:]
        STATE["message"] = msg

def set_state(**kwargs):
    with STATE_LOCK:
        STATE.update(kwargs)

def state_copy():
    with STATE_LOCK:
        out = dict(STATE)
        out["log"] = list(STATE["log"])
        return out

def detect_tools():
    names = ["python","java","apkanalyzer","aapt2","aapt","apksigner","keytool","jadx","apktool","adb","frida","frida-ps","frida-trace","termux-open-url"]
    return {n: bool(shutil.which(n)) for n in names}

def safe_name(name: str) -> str:
    base = Path(name).name.replace("\x00","")
    cleaned = "".join(ch if ch.isalnum() or ch in "._- ()[]" else "_" for ch in base)
    return cleaned[:180] or "target.apk"

def run_cmd_stream(cmd: list[str], stage: str, progress_start: int, progress_end: int) -> int:
    global PROCESS
    set_state(stage=stage, progress=progress_start)
    log("Running: " + " ".join(cmd))
    PROCESS = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert PROCESS.stdout is not None
    count = 0
    for line in PROCESS.stdout:
        line = line.rstrip()
        if line:
            log(line)
        count += 1
        if count % 4 == 0:
            cur = min(progress_end - 1, progress_start + (count // 4))
            set_state(progress=cur)
    rc = PROCESS.wait()
    PROCESS = None
    set_state(progress=progress_end)
    return rc



def frida_state_copy():
    with FRIDA_LOCK:
        return dict(FRIDA_STATE)

def set_frida_state(**kwargs):
    with FRIDA_LOCK:
        FRIDA_STATE.update(kwargs)

def frida_worker(package: str, mode: str, probes: list[str], duration: int, target_id: str):
    global FRIDA_PROCESS
    try:
        set_frida_state(status="running",package=package,mode=mode,message="Starting authorized attach-only Frida observation",started=time.time(),finished=None,exitCode=None)
        for p in (FRIDA_ANALYSIS,FRIDA_EVENTS):
            try:
                if p.exists(): p.unlink()
            except Exception: pass
        cmd=[
            sys.executable,str(FRIDA_RUNNER),"--package",package,"--mode",mode,
            "--probes",",".join(probes),"--duration",str(max(5,min(duration,3600))),
            "--output",str(FRIDA_ANALYSIS),"--events",str(FRIDA_EVENTS),"--authorized"
        ]
        FRIDA_PROCESS=subprocess.Popen(cmd,cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        lines=[]
        if FRIDA_PROCESS.stdout:
            for line in FRIDA_PROCESS.stdout:
                line=line.rstrip()
                if line:
                    lines.append(line)
                    set_frida_state(message=line[-1200:])
        rc=FRIDA_PROCESS.wait()
        FRIDA_PROCESS=None
        if rc!=0:
            set_frida_state(status="error",message=(lines[-1] if lines else f"Frida runner exited {rc}"),finished=time.time(),exitCode=rc)
            return
        if target_id:
            rec=load_target(target_id)
            if rec:
                folder=Path((rec.get("storage") or {}).get("folder",""))
                if folder:
                    folder.mkdir(parents=True,exist_ok=True)
                    if FRIDA_ANALYSIS.exists(): shutil.copy2(FRIDA_ANALYSIS,folder/"frida-analysis.json")
                    if FRIDA_EVENTS.exists(): shutil.copy2(FRIDA_EVENTS,folder/"frida-events.jsonl")
                    rec["outputs"]={**rec.get("outputs",{}),"frida-analysis.json":str(folder/"frida-analysis.json"),"frida-events.jsonl":str(folder/"frida-events.jsonl")}
                    from lola_library import save_target
                    save_target(rec)
        set_frida_state(status="complete",message="Frida observation complete",finished=time.time(),exitCode=0)
    except Exception as exc:
        FRIDA_PROCESS=None
        set_frida_state(status="error",message=str(exc),finished=time.time(),exitCode=1)

def runtime_state_copy():
    with RUNTIME_LOCK:
        return dict(RUNTIME_STATE)

def set_runtime_state(**kwargs):
    with RUNTIME_LOCK:
        RUNTIME_STATE.update(kwargs)

def runtime_worker(package: str, duration: int, target_id: str):
    global RUNTIME_PROCESS
    try:
        set_runtime_state(status="running",package=package,message="Starting read-only ADB/logcat trace",started=time.time(),finished=None,exitCode=None)
        for p in (RUNTIME_ANALYSIS,RUNTIME_EVENTS):
            try:
                if p.exists(): p.unlink()
            except Exception: pass
        cmd=[sys.executable,str(RUNTIME_MONITOR),"--package",package,"--duration",str(max(5,min(duration,3600))),"--output",str(RUNTIME_ANALYSIS),"--events",str(RUNTIME_EVENTS)]
        RUNTIME_PROCESS=subprocess.Popen(cmd,cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        lines=[]
        if RUNTIME_PROCESS.stdout:
            for line in RUNTIME_PROCESS.stdout:
                line=line.rstrip()
                if line:
                    lines.append(line)
                    set_runtime_state(message=line[-1000:])
        rc=RUNTIME_PROCESS.wait()
        RUNTIME_PROCESS=None
        if rc!=0:
            set_runtime_state(status="error",message=(lines[-1] if lines else f"Runtime observer exited {rc}"),finished=time.time(),exitCode=rc)
            return
        if target_id:
            rec=load_target(target_id)
            if rec:
                folder=Path((rec.get("storage") or {}).get("folder",""))
                if folder:
                    folder.mkdir(parents=True,exist_ok=True)
                    if RUNTIME_ANALYSIS.exists(): shutil.copy2(RUNTIME_ANALYSIS,folder/"runtime-analysis.json")
                    if RUNTIME_EVENTS.exists(): shutil.copy2(RUNTIME_EVENTS,folder/"runtime-events.jsonl")
                    rec["outputs"]={**rec.get("outputs",{}),"runtime-analysis.json":str(folder/"runtime-analysis.json"),"runtime-events.jsonl":str(folder/"runtime-events.jsonl")}
                    from lola_library import save_target
                    save_target(rec)
        set_runtime_state(status="complete",message="Realtime observation complete",finished=time.time(),exitCode=0)
    except Exception as exc:
        RUNTIME_PROCESS=None
        set_runtime_state(status="error",message=str(exc),finished=time.time(),exitCode=1)

def scan_worker(target: Path, target_id: str, mode: str, checks: list[str], decompile: bool, keep_decompiled: bool, cleanup: bool):
    analysis = ROOT / "apk-analysis.json"
    report = ROOT / "apk-report.html"
    reader = ROOT / "android-code-reader.json"
    decompiled_dir = ROOT / ".lola-apk" / "decompiled"
    try:
        set_state(
            status="running", stage="validate", target=str(target), targetId=target_id, checks=checks, mode=mode,
            progress=3, started=time.time(), finished=None, exitCode=None,
            report="", analysis=str(analysis), reader=""
        )
        log("Validating APK target")
        set_plan(target_id, checks, mode, {"decompile":decompile,"keepDecompiled":keep_decompiled,"cleanup":cleanup})
        if not ANALYZER.exists():
            raise RuntimeError(f"Missing analyzer: {ANALYZER}")
        if not REPORTER.exists():
            raise RuntimeError(f"Missing report builder: {REPORTER}")
        if not target.exists() or target.suffix.lower() != ".apk":
            raise RuntimeError("Selected file is not an APK")

        set_state(stage="analyze", progress=8)
        cmd = [sys.executable, str(ANALYZER), str(target), "--output", str(analysis), "--checks", ",".join(checks)]
        if decompile or "decompile" in checks or "store_decompiled" in checks:
            cmd.append("--decompile")
        if keep_decompiled or "android_reader" in checks or "store_decompiled" in checks:
            cmd.append("--keep-extracted")

        rc = run_cmd_stream(cmd, "analyze", 8, 76)
        if rc != 0:
            raise RuntimeError(f"APK analyzer exited with code {rc}")

        set_state(stage="report", progress=80)
        rc = run_cmd_stream(
            [sys.executable, str(REPORTER), "--input", str(analysis), "--output", str(report), "--mode", mode],
            "report", 80, 96
        )
        if rc != 0:
            raise RuntimeError(f"Report builder exited with code {rc}")

        if "android_reader" in checks:
            set_state(stage="reader", progress=97)
            log("Building Android Code Reader library")
            build_reader(target, analysis, decompiled_dir if decompiled_dir.exists() else None, reader)
            set_state(reader=str(reader), progress=98)

        stored = archive_artifacts(
            target_id,
            source_apk=target,
            analysis=analysis,
            report=report,
            reader=reader if reader.exists() else None,
            decompiled=decompiled_dir if decompiled_dir.exists() else None,
            keep_apk="store_target" in checks,
            keep_analysis="store_analysis" in checks,
            keep_report="store_report" in checks,
            keep_reader="android_reader" in checks,
            keep_decompiled="store_decompiled" in checks,
        )
        if stored:
            log("Target Library archived: " + ", ".join(sorted(stored.keys())))

        if decompiled_dir.exists() and (cleanup or (not keep_decompiled and "store_decompiled" not in checks)):
            shutil.rmtree(decompiled_dir, ignore_errors=True)
            log("Removed Lola temporary decompiled output")
        if cleanup and "store_target" not in checks and target.exists():
            try:
                target.unlink()
                log("Removed temporary uploaded APK after scan")
            except Exception:
                pass

        finished=time.time()
        try:
            analysis_data=json.loads(analysis.read_text(encoding="utf-8-sig")) if analysis.exists() else {}
        except Exception:
            analysis_data={}
        complete_scan(
            target_id, "complete", mode, checks, analysis_data,
            {"analysis":stored.get("apk-analysis.json",str(analysis)),"report":stored.get("apk-report.html",str(report)),"reader":stored.get("android-code-reader.json",str(reader) if reader.exists() else "")},
            started=STATE.get("started"), finished=finished
        )
        set_state(
            status="complete", stage="complete", progress=100, finished=finished,
            exitCode=0, report=str(report), reader=str(reader) if reader.exists() else ""
        )
        log("APK scan complete")
    except Exception as exc:
        try:
            complete_scan(target_id, "error", mode, checks, None, {}, started=STATE.get("started"), finished=time.time())
        except Exception:
            pass
        log("ERROR: " + str(exc))
        log(traceback.format_exc(limit=3))
        set_state(status="error", stage="error", finished=time.time(), exitCode=1)

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#08111f">
<title>Lola Mobile APK Scanner</title>
<style>
:root{color-scheme:dark;--bg:#07101c;--panel:#101a2d;--panel2:#0b1526;--line:#273a59;--text:#edf4ff;--muted:#9fb1cc;--accent:#77a9ff;--ok:#58d7a7;--warn:#ffc45e;--bad:#ff6b80}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);font:14px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}.wrap{max-width:1000px;margin:auto;padding:12px;padding-bottom:90px}
header{position:sticky;top:0;z-index:20;background:rgba(7,16,28,.94);backdrop-filter:blur(14px);padding:10px 0 8px}h1{font-size:22px;margin:0}.sub{color:var(--muted);font-size:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:13px;margin:10px 0}.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
button,.btn,select,input[type=text]{border:1px solid var(--line);background:#13223c;color:var(--text);border-radius:12px;padding:11px 13px;font:inherit}button{cursor:pointer;font-weight:700}.primary{background:#285fc5}.danger{background:#57202d}.ghost{background:#0b1526}
.filebtn{display:block;text-align:center;border:2px dashed #35517d;background:#0b1629;border-radius:15px;padding:20px;cursor:pointer}.filebtn input{display:none}.fileName{font-weight:800;word-break:break-all;margin-top:7px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.mode{min-height:92px;text-align:left}.mode.active{outline:2px solid var(--accent);background:#1a2b49}.mode b{display:block}.mode small{display:block;color:var(--muted);margin-top:4px}
.opts{display:grid;grid-template-columns:1fr;gap:8px}.check{display:flex;gap:10px;align-items:flex-start;background:#0b1526;border:1px solid var(--line);border-radius:12px;padding:11px}.check input{width:20px;height:20px;flex:0 0 auto}.presetbar{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.libgrid{display:grid;gap:8px}.libitem{background:#0b1526;border:1px solid var(--line);border-radius:12px;padding:10px}.libitem b{display:block}.search{width:100%;margin-top:9px}
.progress{height:14px;background:#07101d;border:1px solid var(--line);border-radius:999px;overflow:hidden}.bar{height:100%;width:0;background:linear-gradient(90deg,#4b83eb,#5ad4ae);transition:width .25s}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}.metric{background:#0b1526;border:1px solid var(--line);border-radius:12px;padding:10px}.metric b{font-size:20px;display:block}.metric span{font-size:11px;color:var(--muted)}
.log{background:#050a12;border:1px solid var(--line);border-radius:12px;padding:10px;white-space:pre-wrap;word-break:break-word;max-height:300px;overflow:auto;font:12px/1.4 ui-monospace,Consolas,monospace}
.bottom{position:fixed;left:0;right:0;bottom:0;background:rgba(7,16,28,.96);backdrop-filter:blur(16px);border-top:1px solid var(--line);padding:9px 12px env(safe-area-inset-bottom)}.bottom .inner{max-width:1000px;margin:auto;display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.bottom button{width:100%}
.hidden{display:none!important}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
@media(min-width:720px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}.opts{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="wrap">
<header><h1>📦 Lola Mobile</h1><div class="sub">Android APK deep scanner · localhost only</div></header>

<div class="card">
  <b>1. Select APK</b>
  <label class="filebtn">
    <input id="apk" type="file" accept=".apk,application/vnd.android.package-archive">
    <div>📂 Tap to choose APK</div>
    <div id="fileName" class="fileName sub">No APK selected</div>
  </label>
  <div id="uploadStatus" class="sub" style="margin-top:7px"></div>
</div>

<div class="card">
  <b>2. What should Lola do with this target?</b>
  <div class="sub">Tick the checks before scanning. The plan is saved into the Target Library.</div>
  <div class="presetbar">
    <button class="ghost" onclick="applyPreset('light')">Light</button>
    <button class="ghost" onclick="applyPreset('recommended')">Recommended</button>
    <button class="ghost" onclick="applyPreset('deep')">Deep</button>
    <button class="ghost" onclick="applyPreset('none')">Clear</button>
  </div>
  <div class="opts" id="planChecks" style="margin-top:10px"></div>
  <div class="sub" id="planSummary" style="margin-top:8px"></div>
</div>

<div class="card">
  <b>3. Choose report view</b>
  <div class="grid" id="modes" style="margin-top:10px"></div>
</div>

<div class="card">
  <b>4. Run options</b>
  <div class="opts" style="margin-top:10px">
    <label class="check"><input id="decompile" type="checkbox"><span><b>JADX decompile</b><small class="sub">Use only if JADX is installed</small></span></label>
    <label class="check"><input id="keep" type="checkbox"><span><b>Keep decompiled code</b><small class="sub">Stores generated source locally</small></span></label>
    <label class="check"><input id="cleanup" type="checkbox"><span><b>Cleanup temporary code</b><small class="sub">Lola-created temporary output only</small></span></label>
    <label class="check"><input id="autoReport" type="checkbox" checked><span><b>Open report when done</b><small class="sub">Opens apk-report.html</small></span></label>
  </div>
</div>

<div class="card">
  <div class="row" style="justify-content:space-between"><b>Scan Status</b><span id="status">Ready</span></div>
  <div class="progress" style="margin-top:10px"><div class="bar" id="bar"></div></div>
  <div class="metrics">
    <div class="metric"><b id="progress">0%</b><span>PROGRESS</span></div>
    <div class="metric"><b id="stage">READY</b><span>STAGE</span></div>
    <div class="metric"><b id="tools">0</b><span>TOOLS READY</span></div>
  </div>
</div>

<div class="card">
  <div class="row" style="justify-content:space-between"><b>Live Log</b><button class="ghost" onclick="clearLog()">Clear</button></div>
  <div id="log" class="log" style="margin-top:9px">Ready.</div>
</div>

<div class="card">
  <b>Local tools</b>
  <div id="toolList" class="sub" style="margin-top:8px">Checking…</div>
</div>
<div class="card" id="libraryCard">
  <div class="row" style="justify-content:space-between"><b>📚 Built-in /library</b><span class="sub" id="libraryCount"></span></div>
  <input class="search" id="librarySearch" type="text" placeholder="Search command, function, output, tool...">
  <div id="storageMap" class="sub" style="margin-top:8px"></div>
  <div class="libgrid" id="commandLibrary" style="margin-top:10px"></div>
</div>

<div class="card" id="readerCard">
  <div class="row" style="justify-content:space-between"><b>📖 Android Code Reader</b><span class="sub" id="readerSummary">Not built yet</span></div>
  <div class="sub">Search manifest/permissions/components, DEX strings, APK resources and retained JADX source from the current target.</div>
  <input class="search" id="readerSearch" type="text" placeholder="Search class, method, URL, API, string, permission, WebView...">
  <div class="presetbar">
    <button class="ghost" onclick="loadReader('main')">Deep-Dive Main</button>
    <button class="ghost" onclick="loadReader('code360')">Code 360</button>
    <button class="ghost" onclick="loadReader('strings')">Code Strings</button>
    <button class="ghost" onclick="loadReader('codeview')">Code View</button>
    <button class="ghost" onclick="loadReader('transparent')">Transparent</button>
    <button class="ghost" onclick="loadReader('trace')">Trace</button>
    <button class="ghost" onclick="loadReader('routes')">Routes</button>
    <button class="ghost" onclick="loadReader('map')">Map</button>
    <button class="ghost" onclick="loadReader('codebrains')">Code Brains</button>
    <button class="ghost" onclick="loadReader('targetcodes')">Target Codes</button>
    <button class="ghost" onclick="loadReader('maincode')">Main Code</button>
    <button class="ghost" onclick="loadReader('urls')">URLs</button>
    <button class="ghost" onclick="loadReader('verify')">Verify</button>
    <button class="ghost" onclick="loadReader('callback')">Callback</button>
    <button class="ghost" onclick="loadReader('fallback')">Fallback</button>
    <button class="ghost" onclick="loadReader('recheck')">Recheck</button>
    <button class="ghost" onclick="loadReader('subscribes')">Subscriptions</button>
    <button class="ghost" onclick="loadReader('payment')">Payment</button>
    <button class="ghost" onclick="loadReader('etc')">Etc</button>
    <button class="ghost" onclick="startRuntime()">Test APK Realtime</button>
    <button class="ghost" onclick="loadReader('resources')">Resources</button>
    <button class="ghost" onclick="loadReader('risk')">Findings</button>
    <button class="danger" onclick="removeGeneratedCode()">Remove Generated</button>
  </div>
  <div class="libgrid" id="readerResults" style="margin-top:10px"></div>
</div>

<div class="card" id="fridaCard">
  <div class="row" style="justify-content:space-between"><b>🧩 Frida Runtime (optional)</b><span class="sub" id="fridaStatus">Idle</span></div>
  <div class="sub">Observation-only instrumentation for an app/test build you own or are authorized to test. Root is optional: choose Frida Gadget for an authorized unrooted test build, or frida-server for a rooted test device.</div>
  <div class="row" style="margin-top:9px">
    <select id="fridaMode">
      <option value="gadget">Unrooted · Frida Gadget</option>
      <option value="root-server">Rooted · frida-server</option>
    </select>
    <input class="search" id="fridaDuration" type="text" value="120" inputmode="numeric" style="max-width:100px">
  </div>
  <label class="check" style="margin-top:8px"><input id="fridaAuthorized" type="checkbox"><span><b>I own/have authorization for this test target</b><small class="sub">Required before Lola will attach Frida.</small></span></label>
  <div class="sub" style="margin-top:8px">Safe probes:</div>
  <div class="opts" id="fridaProbes" style="margin-top:8px"></div>
  <div class="presetbar">
    <button class="primary" onclick="startFrida()">Start Frida</button>
    <button class="danger" onclick="stopFrida()">Stop</button>
    <button class="ghost" onclick="showFrida('all')">All</button>
    <button class="ghost" onclick="showFrida('url')">URLs</button>
    <button class="ghost" onclick="showFrida('lifecycle')">Lifecycle</button>
    <button class="ghost" onclick="showFrida('storage')">Storage</button>
    <button class="ghost" onclick="showFrida('crypto')">Crypto</button>
    <button class="ghost" onclick="showFrida('billing')">Billing</button>
    <button class="ghost" onclick="showFrida('methods')">Methods</button>
  </div>
  <div class="libgrid" id="fridaResults" style="margin-top:10px"></div>
  <div class="sub" style="margin-top:8px">Excluded by design: pinning bypass, root/Frida hiding, purchase/subscription tampering, secret-key dumping, and response manipulation.</div>
</div>

<div class="card" id="runtimeCard">
  <div class="row" style="justify-content:space-between"><b>⏱ Realtime APK Test</b><span class="sub" id="runtimeStatus">Idle</span></div>
  <div class="sub">Read-only ADB/logcat observation for the selected installed test package. Open the app manually first. No purchase/subscription state is changed.</div>
  <div class="row" style="margin-top:9px">
    <input class="search" id="runtimePackage" type="text" placeholder="Package name, e.g. com.example.app" style="flex:1">
    <input class="search" id="runtimeDuration" type="text" value="120" inputmode="numeric" style="max-width:100px">
    <button class="primary" onclick="startRuntime()">Start Realtime</button>
    <button class="danger" onclick="stopRuntime()">Stop</button>
  </div>
  <div class="presetbar">
    <button class="ghost" onclick="showRuntime('all')">Traces</button>
    <button class="ghost" onclick="showRuntime('billing')">Payment</button>
    <button class="ghost" onclick="showRuntime('subscription')">Subscriptions</button>
    <button class="ghost" onclick="showRuntime('callback')">Callbacks</button>
    <button class="ghost" onclick="showRuntime('fallback')">Fallback</button>
    <button class="ghost" onclick="showRuntime('verify')">Verify/Recheck</button>
    <button class="ghost" onclick="showRuntime('error')">Errors</button>
  </div>
  <div class="libgrid" id="runtimeResults" style="margin-top:10px"></div>
</div>

<div class="card">
  <div class="row" style="justify-content:space-between"><b>🎯 Target Library</b><button class="ghost" onclick="refreshTargets()">Refresh</button></div>
  <div class="sub">Stored details: .lola-library/targets/&lt;target-id&gt;/target.json</div>
  <div class="libgrid" id="targetLibrary" style="margin-top:10px"></div>
</div>

<div class="card">
  <div class="row" style="justify-content:space-between"><b>🗂 Target Detail</b><span class="sub" id="targetDetailTitle">Select a saved target</span></div>
  <div class="libgrid" id="targetDetail" style="margin-top:10px"></div>
</div>
</div>

<div class="bottom"><div class="inner">
  <button class="primary" id="runBtn" onclick="runScan()">▶ RUN</button>
  <button class="danger" onclick="stopScan()">■ STOP</button>
  <button id="reportBtn" onclick="openReport()" disabled>REPORT</button>
  <button onclick="openLibrary()">LIBRARY</button>
</div></div>

<script>
const MODES=__MODES__;
let selectedMode='/apk360', uploadedPath='', targetId='', lastStatus='idle', opened=false;
let LIB={commands:[],functions:[],apkPlan:[],storage:{}};
let selectedChecks=new Set();
let FRIDALIB={modes:[],tools:[],probes:[],safety:{}};
let selectedFridaProbes=new Set(['overview','classes','methods','lifecycle','urls','dns','intents','storage','crypto','billing','callbacks','timers']);
const $=id=>document.getElementById(id);


function renderPlan(){
  const root=$('planChecks');root.replaceChildren();
  (LIB.apkPlan||[]).forEach(x=>{
    const lab=document.createElement('label');lab.className='check';
    const cb=document.createElement('input');cb.type='checkbox';cb.checked=selectedChecks.has(x.id);
    cb.onchange=()=>{if(cb.checked)selectedChecks.add(x.id);else selectedChecks.delete(x.id);renderPlanSummary()};
    const span=document.createElement('span');
    span.innerHTML='<b>'+x.label+'</b><small class="sub">'+x.description+' · cost '+x.cost+'</small>';
    lab.append(cb,span);root.appendChild(lab);
  });
  renderPlanSummary();
}
function renderPlanSummary(){
  const labels=(LIB.apkPlan||[]).filter(x=>selectedChecks.has(x.id)).map(x=>x.label);
  $('planSummary').textContent=labels.length?labels.length+' selected · '+labels.join(' · '):'No checks selected';
  $('decompile').checked=selectedChecks.has('decompile');
}
function applyPreset(name){
  selectedChecks.clear();
  const plan=LIB.apkPlan||[];
  if(name==='light'){
    ['identity','manifest','permissions','components','files','store_target'].forEach(x=>selectedChecks.add(x));
  }else if(name==='recommended'){
    plan.filter(x=>x.default).forEach(x=>selectedChecks.add(x.id));
  }else if(name==='deep'){
    plan.forEach(x=>selectedChecks.add(x.id));
  }
  renderPlan();
}
function renderCommandLibrary(){
  const q=$('librarySearch').value.trim().toLowerCase();
  const root=$('commandLibrary');root.replaceChildren();
  const items=[...(LIB.commands||[]),...(LIB.functions||[])].filter(x=>!q||JSON.stringify(x).toLowerCase().includes(q));
  $('libraryCount').textContent=items.length+' commands/functions';
  items.slice(0,120).forEach(x=>{
    const d=document.createElement('div');d.className='libitem';
    d.innerHTML='<b>'+x.label+' <span class="sub">'+x.id+'</span></b>'+
      '<div>'+x.purpose+'</div>'+
      '<div class="sub">'+(x.group||'Function')+' · cost '+(x.cost||'-')+' · tools '+((x.tools||[]).join(', ')||'none')+' · outputs '+((x.outputs||[]).join(', ')||'none')+(x.module?' · module '+x.module:'')+'</div>';
    if(x.id.startsWith('/apk')){
      d.onclick=()=>{selectedMode=x.id;renderModes();window.scrollTo({top:0,behavior:'smooth'})};
      d.style.cursor='pointer';
    } else {
      const readerMap={
        '/deep-dive main':'main','/code360':'code360','/codestring':'strings','/codeview':'codeview',
        '/codetransparent':'transparent','/trace':'trace','/routes':'routes','/map':'map',
        '/codebrains':'codebrains','/targetcodes':'targetcodes','/maincode':'maincode','/urls':'urls',
        '/verify':'verify','/callback':'callback','/fallback':'fallback','/recheck':'recheck',
        '/subscribes':'subscribes','/payment':'payment','/etc':'etc','/androidreader':'main',
        '/readersource':'codeview','/readerresources':'resources','/readerdex':'dex','/traces':'trace'
      };
      if(readerMap[x.id]){
        d.onclick=()=>{loadReader(readerMap[x.id]);$('readerCard').scrollIntoView({behavior:'smooth',block:'start'})};
        d.style.cursor='pointer';
      } else if(x.id==='/coderemove'){
        d.onclick=removeGeneratedCode;d.style.cursor='pointer';
      } else if(x.id==='/test apk realtime'){
        d.onclick=()=>{$('runtimeCard').scrollIntoView({behavior:'smooth',block:'start'});startRuntime()};d.style.cursor='pointer';
      } else if(String(x.id||'').startsWith('/frida')){
        d.onclick=()=>{$('fridaCard').scrollIntoView({behavior:'smooth',block:'start'})};d.style.cursor='pointer';
      }
    }
    root.appendChild(d);
  });
  if(!root.children.length)root.innerHTML='<div class="libitem sub">No matching library command.</div>';
}
async function refreshTargets(){
  try{
    const r=await fetch('/api/targets?t='+Date.now(),{cache:'no-store'});const j=await r.json();
    const root=$('targetLibrary');root.replaceChildren();
    (j.targets||[]).forEach(x=>{
      const d=document.createElement('div');d.className='libitem';
      d.innerHTML='<b>'+x.name+'</b><div class="sub">'+x.id+' · '+Math.round((x.size||0)/1024/1024)+' MB · scans '+(x.scanCount||0)+'</div>'+
        '<div>Package: '+(x.package||'-')+' · Risk: '+(x.riskFindings||0)+' · Last: '+(x.lastStatus||'-')+'</div>';
      d.onclick=()=>loadTargetRecord(x.id);d.style.cursor='pointer';root.appendChild(d);
    });
    if(!root.children.length)root.innerHTML='<div class="libitem sub">No saved targets yet.</div>';
  }catch{}
}
async function loadTargetRecord(id){
  const r=await fetch('/api/target?id='+encodeURIComponent(id));const j=await r.json();
  if(!r.ok)return;
  targetId=j.id||targetId;
  if(j.lastPlan?.length){selectedChecks=new Set(j.lastPlan);renderPlan()}
  selectedMode=j.lastMode||selectedMode;renderModes();
  $('targetDetailTitle').textContent=(j.name||id)+' · '+(j.id||'');
  if(j.apk?.package)$('runtimePackage').value=j.apk.package;
  const root=$('targetDetail');root.replaceChildren();
  const rows=[
    ['SHA-256',j.sha256||''],
    ['Size',Math.round((j.size||0)/1024/1024)+' MB'],
    ['Current upload path',j.storedPath||'-'],
    ['Last status',j.lastStatus||'-'],
    ['Package',j.apk?.package||'-'],
    ['SDK','min '+(j.apk?.minSdk||'-')+' / target '+(j.apk?.targetSdk||'-')],
    ['Risk findings',String(j.apk?.riskFindings||0)],
    ['Last plan',(j.lastPlan||[]).join(', ')||'-'],
    ['Storage folder',j.storage?.folder||'-'],
    ['Stored APK',j.storage?.apk||'-'],
    ['Analysis',j.storage?.analysis||'-'],
    ['Report',j.storage?.report||'-'],
    ['Android reader',j.storage?.reader||'-'],
    ['Decompiled source',j.storage?.decompiled||'-'],
    ['Runtime analysis',j.storage?.runtimeAnalysis||j.outputs?.['runtime-analysis.json']||'-'],
    ['Runtime events',j.storage?.runtimeEvents||j.outputs?.['runtime-events.jsonl']||'-'],
    ['Frida analysis',j.storage?.fridaAnalysis||j.outputs?.['frida-analysis.json']||'-'],
    ['Frida events',j.storage?.fridaEvents||j.outputs?.['frida-events.jsonl']||'-'],
    ['Scan history',String((j.scans||[]).length)]
  ];
  rows.forEach(x=>readerItem(root,x[0],'',x[1]));
  const retainedApk=j.outputs?.['target.apk']||'';
  if(retainedApk){
    uploadedPath=retainedApk;
    $('fileName').textContent='Library target: '+(j.name||id);
    $('uploadStatus').textContent='Using retained library APK · '+retainedApk;
  } else {
    uploadedPath='';
    $('uploadStatus').textContent='Target details loaded. APK binary was not retained; choose the APK again to rescan.';
  }
  loadReader('overview');
}
async function initLibrary(){
  try{
    const r=await fetch('/api/library',{cache:'no-store'});LIB=await r.json();
    applyPreset('recommended');renderCommandLibrary();refreshTargets();loadFridaLibrary();
    const storage=LIB.storage||{};
    $('storageMap').innerHTML='<b>Target storage:</b> '+(storage.targetPattern||'.lola-library/targets/&lt;target-id&gt;/target.json')+
      '<br>Analysis: '+(storage.analysis||'-')+'<br>Report: '+(storage.report||'-')+'<br>Reader: '+(storage.reader||'-');
  }catch{}
}


async function fetchReader(){
  if(!targetId)return null;
  const r=await fetch('/api/reader?id='+encodeURIComponent(targetId)+'&t='+Date.now(),{cache:'no-store'});
  if(!r.ok)return null;
  return await r.json();
}
function readerItem(root,title,meta,body){
  const d=document.createElement('div');d.className='libitem';
  const b=document.createElement('b');b.textContent=title;d.appendChild(b);
  if(meta){const m=document.createElement('div');m.className='sub';m.textContent=meta;d.appendChild(m)}
  if(body){const x=document.createElement('div');x.style.whiteSpace='pre-wrap';x.style.wordBreak='break-word';x.textContent=body;d.appendChild(x)}
  root.appendChild(d);
}
async function loadReader(view='main'){
  const data=await fetchReader(),root=$('readerResults');root.replaceChildren();
  if(!data){root.innerHTML='<div class="libitem sub">Reader not built for this target yet. Tick "Build Android Code Reader" and scan.</div>';return}
  const s=data.summary||{},sections=data.sections||{};
  if(s.package&&!$('runtimePackage').value)$('runtimePackage').value=s.package;
  $('readerSummary').textContent=(s.sourceFiles||0)+' source · '+(s.resourcePreviews||0)+' resources · '+(s.dexStrings||0)+' DEX · '+(s.traceEdges||0)+' links';
  if(view==='main'){
    [
      ['Target',s.package||'-','SHA-256 '+(s.sha256||'-')],
      ['Code',String(s.sourceFiles||0)+' source files',(s.sourceClasses||0)+' classes · '+(s.sourceMethods||0)+' methods'],
      ['Strings',String(s.codeStrings||0)+' indexed','DEX '+(s.dexStrings||0)+' · resources '+(s.resourcePreviews||0)],
      ['Flow',String(s.traceEdges||0)+' links',String(s.routes||0)+' routes'],
      ['Permissions',String(sections.permissions?.items?.length||0),'Sensitive '+String(sections.permissions?.sensitive?.length||0)],
      ['Components',String(sections.components?.items?.length||0),'Exported '+String(sections.components?.exported?.length||0)],
      ['Network',String(sections.urls?.items?.length||0)+' URLs',String(sections.api?.items?.length||0)+' API refs'],
      ['Signals',String(sections.webview?.items?.length||0)+' WebView',String(sections.crypto?.items?.length||0)+' crypto'],
      ['Findings',String(sections.risk?.items?.length||0),'Static review signals']
    ].forEach(x=>readerItem(root,x[0],x[1],x[2]));
  }else if(view==='code360'){
    const brain=data.codeBrains||{};
    Object.entries({...s,...brain}).forEach(([k,v])=>readerItem(root,k,'',typeof v==='object'?JSON.stringify(v,null,2):String(v)));
  }else if(view==='strings'){
    (data.codeStrings||[]).slice(0,250).forEach(x=>readerItem(root,x.value||'string',x.kind+' · '+(x.location||''),''));
  }else if(view==='codeview'){
    (data.sourceFiles||[]).slice(0,160).forEach(x=>readerItem(root,x.path,(x.lines||'?')+' lines · '+(x.extension||''),x.preview||'[JADX/source preview unavailable]'));
    if(!root.children.length)(data.resources||[]).slice(0,120).forEach(x=>readerItem(root,x.path,(x.bytes||0)+' bytes',x.preview||''));
  }else if(view==='transparent'){
    const t=data.transparent||{};
    (t.edges||[]).slice(0,250).forEach(x=>readerItem(root,x.relation||'link',(x.from||'')+' → '+(x.to||''),x.evidence||''));
  }else if(view==='trace'){
    (data.trace||[]).slice(0,250).forEach(x=>readerItem(root,x.relation||'trace',(x.from||'')+' → '+(x.to||''),x.evidence||''));
  }else if(view==='routes'){
    (data.routes||[]).slice(0,250).forEach(x=>readerItem(root,x.kind||'route',x.source||'',JSON.stringify(x,null,2)));
  }else if(view==='map'){
    const m=data.map||{};
    readerItem(root,'Map summary',(m.nodes?.length||0)+' nodes · '+(m.edges?.length||0)+' edges','Logical static map; no target code is executed.');
    (m.edges||[]).slice(0,250).forEach(x=>readerItem(root,x.relation||'edge',(x.from||'')+' → '+(x.to||''),x.evidence||''));
  }else if(view==='codebrains'){
    const b=data.codeBrains||{};
    Object.entries(b).forEach(([k,v])=>readerItem(root,k,'',typeof v==='object'?JSON.stringify(v,null,2):String(v)));
  }else if(view==='targetcodes'){
    const t=data.targetCodes||{};
    readerItem(root,'Source files',String(t.source?.length||0),JSON.stringify((t.source||[]).slice(0,120),null,2));
    readerItem(root,'Resources',String(t.resources?.length||0),JSON.stringify((t.resources||[]).slice(0,120),null,2));
    readerItem(root,'DEX files',String(t.dexFiles?.length||0),JSON.stringify(t.dexFiles||[],null,2));
    readerItem(root,'Native libraries','',JSON.stringify(t.native||{},null,2));
    readerItem(root,'Analysis sections','',JSON.stringify(t.analysisSections||[],null,2));
  }else if(view==='maincode'){
    const m=data.mainCode||{};
    readerItem(root,'Entry points',String(m.entryPoints?.length||0),JSON.stringify((m.entryPoints||[]).slice(0,120),null,2));
    readerItem(root,'Billing/runtime files',String(m.billingFiles?.length||0),(m.billingFiles||[]).join('\n'));
    (m.files||[]).slice(0,120).forEach(x=>readerItem(root,x.path,(x.classes||[]).join(', '),(x.methods||[]).slice(0,80).join(', ')));
  }else if(view==='verify'){
    const v=data.verification||{};
    Object.entries(v).forEach(([k,val])=>readerItem(root,k,'',typeof val==='object'?JSON.stringify(val,null,2):String(val)));
    ((data.billing||{}).verify?.items||[]).slice(0,180).forEach(x=>readerItem(root,'verify',x.location||'',x.preview||''));
  }else if(view==='callback'){
    ((data.billing||{}).callback?.items||[]).slice(0,200).forEach(x=>readerItem(root,'callback',x.location||'',x.preview||''));
  }else if(view==='fallback'){
    ((data.billing||{}).fallback?.items||[]).slice(0,200).forEach(x=>readerItem(root,'fallback',x.location||'',x.preview||''));
  }else if(view==='recheck'){
    ((data.billing||{}).recheck?.items||[]).slice(0,200).forEach(x=>readerItem(root,'recheck',x.location||'',x.preview||''));
  }else if(view==='subscribes'){
    ((data.billing||{}).subscribes?.items||[]).slice(0,220).forEach(x=>readerItem(root,'subscription',x.location||'',x.preview||''));
  }else if(view==='payment'){
    ((data.billing||{}).payment?.items||[]).slice(0,220).forEach(x=>readerItem(root,'payment',x.location||'',x.preview||''));
  }else if(view==='etc'){
    readerItem(root,'Tools','',JSON.stringify(data.sections?.files||{},null,2));
    readerItem(root,'Native','',JSON.stringify(data.sections?.native||{},null,2));
    readerItem(root,'Certificates','',JSON.stringify(data.sections?.certs||{},null,2));
    readerItem(root,'Risk','',JSON.stringify(data.sections?.risk||{},null,2));
  }else if(view==='overview'){
    Object.entries(s).forEach(([k,v])=>readerItem(root,k,'',typeof v==='object'?JSON.stringify(v):String(v)));
  }else if(view==='source'){
    (data.sourceFiles||[]).slice(0,120).forEach(x=>readerItem(root,x.path,(x.lines||'?')+' lines · '+(x.extension||''),x.preview||'[preview unavailable]'));
  }else if(view==='resources'){
    (data.resources||[]).slice(0,120).forEach(x=>readerItem(root,x.path,(x.bytes||0)+' bytes · '+(x.extension||''),x.preview||''));
  }else if(view==='dex'){
    (data.dexStrings||[]).slice(0,180).forEach(x=>readerItem(root,x.value||'DEX string',(x.dex||'')+' @ '+(x.offset||0),''));
  }else if(view==='urls'){
    [...(sections.urls?.items||[]),...(sections.api?.items||[])].slice(0,180).forEach(x=>readerItem(root,x.url||x.preview||'URL/API',x.entry||'',JSON.stringify(x)));
  }else if(view==='risk'){
    (sections.risk?.items||[]).slice(0,180).forEach(x=>readerItem(root,(x.severity||'INFO')+' · '+(x.area||'finding'),x.message||'',typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||{})));
  }
  if(!root.children.length)root.innerHTML='<div class="libitem sub">No entries for this reader view.</div>';
}
async function removeGeneratedCode(){
  if(!targetId){alert('Select a target first.');return}
  if(!confirm('Remove Lola-generated Android Code Reader and retained/generated JADX source for this target? The original APK, analysis/report history and external logs will not be deleted.'))return;
  const r=await fetch('/api/reader/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({targetId})});
  const j=await r.json();
  if(!r.ok){alert(j.error||'Could not remove generated code');return}
  $('readerResults').innerHTML='<div class="libitem sub">Generated reader/JADX artifacts removed for this target.</div>';
  $('readerSummary').textContent='Generated code removed';
  refreshTargets();
}
async function searchReader(){
  const q=$('readerSearch').value.trim(),root=$('readerResults');root.replaceChildren();
  if(!q){loadReader('overview');return}
  if(!targetId){root.innerHTML='<div class="libitem sub">Choose a target first.</div>';return}
  const r=await fetch('/api/reader/search?id='+encodeURIComponent(targetId)+'&q='+encodeURIComponent(q),{cache:'no-store'});
  const j=await r.json();
  (j.results||[]).forEach(x=>readerItem(root,x.kind+' · '+x.title,x.location||'',x.preview||''));
  if(!root.children.length)root.innerHTML='<div class="libitem sub">No reader matches.</div>';
}
$('readerSearch').oninput=()=>{clearTimeout(window.__readerTimer);window.__readerTimer=setTimeout(searchReader,300)};



let fridaCache={events:[],counts:{}};
async function loadFridaLibrary(){
  try{
    const r=await fetch('/api/frida/library',{cache:'no-store'});FRIDALIB=await r.json();
    const root=$('fridaProbes');root.replaceChildren();
    (FRIDALIB.probes||[]).forEach(p=>{
      const lab=document.createElement('label');lab.className='check';
      const cb=document.createElement('input');cb.type='checkbox';cb.checked=selectedFridaProbes.has(p.id);
      cb.onchange=()=>{if(cb.checked)selectedFridaProbes.add(p.id);else selectedFridaProbes.delete(p.id)};
      const span=document.createElement('span');span.innerHTML='<b>'+p.label+'</b><small class="sub">'+p.description+'</small>';
      lab.append(cb,span);root.appendChild(lab);
    });
  }catch{}
}
async function startFrida(){
  if(!targetId){alert('Select/scan a target first.');return}
  if(!$('fridaAuthorized').checked){alert('Confirm that you own or are authorized to instrument this test target.');return}
  const pkg=$('runtimePackage').value.trim();
  if(!pkg){alert('Package name is missing. Run APK analysis first.');return}
  const mode=$('fridaMode').value;
  const duration=Math.max(5,Math.min(parseInt($('fridaDuration').value||'120',10)||120,3600));
  const probes=[...selectedFridaProbes];
  if(!probes.length){alert('Select at least one Frida probe.');return}
  const r=await fetch('/api/frida/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({targetId,package:pkg,mode,duration,probes,authorized:true})});
  const j=await r.json();if(!r.ok){alert(j.error||'Could not start Frida');return}
  $('fridaStatus').textContent='Starting…';$('fridaCard').scrollIntoView({behavior:'smooth',block:'start'});
}
async function stopFrida(){await fetch('/api/frida/stop',{method:'POST'})}
async function pollFrida(){
  try{
    const r=await fetch('/api/frida/status?t='+Date.now(),{cache:'no-store'}),j=await r.json();
    fridaCache=j;$('fridaStatus').textContent=(j.status||'idle')+' · '+(j.message||'');
    if(j.status==='running'||j.status==='complete'||j.status==='error')showFrida(window.__fridaFilter||'all',false);
  }catch{}
  setTimeout(pollFrida,900);
}
function showFrida(filter='all',remember=true){
  if(remember)window.__fridaFilter=filter;
  const root=$('fridaResults');root.replaceChildren();
  const counts=fridaCache.counts||{};
  if(filter==='all')readerItem(root,'Counts','',JSON.stringify(counts,null,2));
  (fridaCache.events||[]).filter(x=>filter==='all'||String(x.kind||'')===filter).slice(-180).forEach(x=>readerItem(root,x.kind||'event',new Date((x.time||0)).toLocaleTimeString(),JSON.stringify(x.data||{},null,2)));
  if(!root.children.length)root.innerHTML='<div class="libitem sub">No matching Frida evidence yet. Open the authorized test app manually, then start Frida.</div>';
}

let runtimeCache={events:[],counts:{}};
async function startRuntime(){
  if(!targetId){alert('Select/scan a target first.');return}
  const pkg=$('runtimePackage').value.trim();
  if(!pkg){alert('Package name is missing. Run APK analysis first or enter the installed test package name.');return}
  const duration=Math.max(5,Math.min(parseInt($('runtimeDuration').value||'120',10)||120,3600));
  const r=await fetch('/api/runtime/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({targetId,package:pkg,duration})});
  const j=await r.json();if(!r.ok){alert(j.error||'Could not start realtime test');return}
  $('runtimeStatus').textContent='Starting…';
  $('runtimeCard').scrollIntoView({behavior:'smooth',block:'start'});
}
async function stopRuntime(){await fetch('/api/runtime/stop',{method:'POST'})}
async function pollRuntime(){
  try{
    const r=await fetch('/api/runtime/status?t='+Date.now(),{cache:'no-store'}),j=await r.json();
    runtimeCache=j;$('runtimeStatus').textContent=(j.status||'idle')+' · '+(j.message||'');
    if(j.package&&!$('runtimePackage').value)$('runtimePackage').value=j.package;
    if(j.status==='running'||j.status==='complete'||j.status==='error')showRuntime(window.__runtimeFilter||'all',false);
  }catch{}
  setTimeout(pollRuntime,900);
}
function showRuntime(filter='all',remember=true){
  if(remember)window.__runtimeFilter=filter;
  const root=$('runtimeResults');root.replaceChildren();
  const counts=runtimeCache.counts||{};
  if(filter==='all')readerItem(root,'Counts','',JSON.stringify(counts,null,2));
  (runtimeCache.events||[]).filter(x=>filter==='all'||(x.categories||[]).includes(filter)||(filter==='verify'&&(x.categories||[]).some(y=>['verify','callback'].includes(y)))).slice(-180).forEach(x=>readerItem(root,(x.categories||[]).join(', '),new Date((x.time||0)*1000).toLocaleTimeString(),x.line||''));
  if(!root.children.length)root.innerHTML='<div class="libitem sub">No matching runtime evidence yet. Open the installed test app manually, then start Realtime Test.</div>';
}

function renderModes(){
  const root=$('modes');root.replaceChildren();
  MODES.forEach(([mode,label,desc])=>{
    const b=document.createElement('button');b.className='mode'+(mode===selectedMode?' active':'');
    b.innerHTML='<b>'+label+'</b><small>'+mode+'<br>'+desc+'</small>';
    b.onclick=()=>{selectedMode=mode;renderModes()};
    root.appendChild(b);
  });
}
$('apk').onchange=async e=>{
  const file=e.target.files?.[0]; if(!file)return;
  $('fileName').textContent=file.name+' · '+Math.round(file.size/1024/1024)+' MB';
  $('uploadStatus').textContent='Uploading to Lola localhost…';
  const r=await fetch('/api/upload',{
    method:'POST',
    headers:{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(file.name),'X-Size':String(file.size)},
    body:file
  });
  const j=await r.json();
  if(!r.ok){$('uploadStatus').textContent='Upload failed: '+(j.error||r.status);return}
  uploadedPath=j.path;targetId=j.targetId||'';$('uploadStatus').textContent='Ready: '+j.name+' · Library ID '+(targetId||'-');
  if(j.lastPlan?.length){selectedChecks=new Set(j.lastPlan);renderPlan()}
  loadReader('overview');refreshTargets();
};
async function runScan(){
  if(!uploadedPath){alert('Choose and upload an APK first.');return}
  opened=false;
  const checks=[...selectedChecks];
  if(!checks.length){alert('Select at least one target check, or choose Light/Recommended/Deep.');return}
  if($('decompile').checked&&!selectedChecks.has('decompile'))selectedChecks.add('decompile');
  const body={target:uploadedPath,targetId,mode:selectedMode,checks:[...selectedChecks],decompile:$('decompile').checked,keepDecompiled:$('keep').checked,cleanup:$('cleanup').checked};
  const r=await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j=await r.json();if(!r.ok)alert(j.error||'Could not start scan');
}
$('decompile').onchange=()=>{if($('decompile').checked)selectedChecks.add('decompile');else selectedChecks.delete('decompile');renderPlan()};
$('librarySearch').oninput=renderCommandLibrary;
async function stopScan(){await fetch('/api/stop',{method:'POST'})}
function openReport(){location.href='/apk-report.html?t='+Date.now()}
function openLibrary(){$('libraryCard').scrollIntoView({behavior:'smooth',block:'start'});setTimeout(()=>$('librarySearch').focus(),350)}
function clearLog(){$('log').textContent=''}
async function poll(){
  try{
    const r=await fetch('/api/status?t='+Date.now(),{cache:'no-store'});const s=await r.json();
    $('status').textContent=s.status||'idle';$('progress').textContent=(s.progress||0)+'%';$('stage').textContent=String(s.stage||'').toUpperCase();$('bar').style.width=(s.progress||0)+'%';
    $('log').textContent=(s.log||[]).join('\n')||'Ready.';$('log').scrollTop=$('log').scrollHeight;
    const toolEntries=Object.entries(s.tools||{});$('tools').textContent=toolEntries.filter(x=>x[1]).length;
    $('toolList').innerHTML=toolEntries.map(([k,v])=>'<span class="'+(v?'ok':'warn')+'">'+(v?'●':'○')+' '+k+'</span>').join(' &nbsp; ');
    $('reportBtn').disabled=!s.report;
    if(s.status==='complete'&&lastStatus!=='complete'){
      loadReader('overview');refreshTargets();
      if($('autoReport').checked&&!opened){opened=true;setTimeout(openReport,500)}
    }
    lastStatus=s.status;
  }catch{}
  setTimeout(poll,700);
}
renderModes();initLibrary();poll();pollRuntime();pollFrida();
</script>
</body></html>
""".replace("__MODES__", json.dumps(APK_MODES))

class Handler(BaseHTTPRequestHandler):
    server_version = "LolaMobile/1.0"

    def log_message(self, fmt, *args):
        pass

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body: bytes, ctype: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in {"/","/library"}:
            return self.send_bytes(INDEX_HTML.encode("utf-8"),"text/html; charset=utf-8")
        if path == "/api/status":
            s = state_copy()
            s["tools"] = detect_tools()
            return self.send_json(s)
        if path == "/api/library":
            return self.send_json(catalog())
        if path == "/api/targets":
            return self.send_json({"targets":list_targets()})
        if path == "/api/target":
            qs=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            tid=(qs.get("id") or [""])[0]
            rec=load_target(tid)
            return self.send_json(rec if rec else {"error":"Target not found"},200 if rec else 404)
        if path == "/api/reader":
            qs=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            tid=(qs.get("id") or [STATE.get("targetId","")])[0]
            rec=load_target(tid) if tid else None
            candidates=[]
            if rec:
                candidates.append(Path((rec.get("storage") or {}).get("reader","")))
                candidates.append(Path((rec.get("outputs") or {}).get("android-code-reader.json","")))
            candidates.append(ROOT/"android-code-reader.json")
            for rp in candidates:
                if str(rp) and rp.exists() and rp.is_file():
                    try:return self.send_json(json.loads(rp.read_text(encoding="utf-8-sig")))
                    except Exception:pass
            return self.send_json({"error":"Reader not found"},404)
        if path == "/api/reader/search":
            qs=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            tid=(qs.get("id") or [STATE.get("targetId","")])[0]
            q=(qs.get("q") or [""])[0]
            rec=load_target(tid) if tid else None
            candidates=[]
            if rec:
                candidates.append(Path((rec.get("storage") or {}).get("reader","")))
                candidates.append(Path((rec.get("outputs") or {}).get("android-code-reader.json","")))
            candidates.append(ROOT/"android-code-reader.json")
            for rp in candidates:
                if str(rp) and rp.exists() and rp.is_file():
                    try:
                        data=json.loads(rp.read_text(encoding="utf-8-sig"))
                        return self.send_json({"results":search_reader(data,q,200)})
                    except Exception:pass
            return self.send_json({"results":[]})
        if path == "/api/frida/library":
            return self.send_json(frida_catalog())
        if path == "/api/frida/status":
            state=frida_state_copy()
            events=[]
            counts={}
            if FRIDA_ANALYSIS.exists():
                try:
                    data=json.loads(FRIDA_ANALYSIS.read_text(encoding="utf-8-sig"))
                    counts=data.get("counts",{})
                    events=data.get("events",[])
                except Exception: pass
            if FRIDA_EVENTS.exists():
                try:
                    lines=FRIDA_EVENTS.read_text(encoding="utf-8",errors="ignore").splitlines()[-250:]
                    events=[json.loads(x) for x in lines if x.strip()]
                    counts={}
                    for ev in events:
                        kind=str(ev.get("kind") or "message")
                        counts[kind]=counts.get(kind,0)+1
                except Exception: pass
            return self.send_json({**state,"events":events,"counts":counts})
        if path == "/api/runtime/status":
            state=runtime_state_copy()
            events=[]
            counts={}
            if RUNTIME_ANALYSIS.exists():
                try:
                    data=json.loads(RUNTIME_ANALYSIS.read_text(encoding="utf-8-sig"))
                    counts=data.get("counts",{})
                    events=data.get("events",[])
                except Exception: pass
            if RUNTIME_EVENTS.exists():
                try:
                    lines=RUNTIME_EVENTS.read_text(encoding="utf-8",errors="ignore").splitlines()[-250:]
                    events=[json.loads(x) for x in lines if x.strip()]
                    counts={}
                    for ev in events:
                        for cat in ev.get("categories",[]): counts[cat]=counts.get(cat,0)+1
                except Exception: pass
            return self.send_json({**state,"events":events,"counts":counts})
        if path == "/apk-report.html":
            p = ROOT / "apk-report.html"
            if not p.exists():
                return self.send_json({"error":"Report not ready"},404)
            return self.send_bytes(p.read_bytes(),"text/html; charset=utf-8")
        if path == "/apk-analysis.json":
            p = ROOT / "apk-analysis.json"
            if not p.exists():
                return self.send_json({"error":"Analysis not ready"},404)
            return self.send_bytes(p.read_bytes(),"application/json; charset=utf-8")
        return self.send_json({"error":"Not found"},404)

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/upload":
            if STATE.get("status") == "running":
                return self.send_json({"error":"A scan is running"},409)
            try:
                size = int(self.headers.get("Content-Length","0"))
                expected = int(self.headers.get("X-Size","0") or 0)
                if size <= 0 or size > MAX_UPLOAD:
                    return self.send_json({"error":"Invalid or oversized upload"},413)
                if expected and expected != size:
                    return self.send_json({"error":"Upload size mismatch"},400)
                name = safe_name(urllib.parse.unquote(self.headers.get("X-Filename","target.apk")))
                if not name.lower().endswith(".apk"):
                    return self.send_json({"error":"Please choose an .apk file"},400)
                UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
                temp_dest = UPLOAD_DIR / ("upload_" + str(time.time_ns()) + ".apk")
                remaining = size
                with temp_dest.open("wb") as f:
                    while remaining:
                        chunk = self.rfile.read(min(1024*1024, remaining))
                        if not chunk:
                            break
                        f.write(chunk); remaining -= len(chunk)
                if remaining != 0:
                    temp_dest.unlink(missing_ok=True)
                    return self.send_json({"error":"Upload incomplete"},400)
                rec=register_target(temp_dest, name)
                final_dest=UPLOAD_DIR / f"{rec['id']}_{name}"
                if final_dest.exists():
                    temp_dest.unlink(missing_ok=True)
                else:
                    temp_dest.replace(final_dest)
                rec=register_target(final_dest, name)
                log(f"APK uploaded: {name} · library {rec['id']}")
                set_state(target=str(final_dest), targetId=rec["id"], checks=rec.get("lastPlan",[]), status="idle", stage="uploaded", progress=0)
                return self.send_json({"ok":True,"name":name,"path":str(final_dest),"targetId":rec["id"],"sha256":rec["sha256"],"lastPlan":rec.get("lastPlan",[])})
            except Exception as exc:
                return self.send_json({"error":str(exc)},500)

        if path == "/api/scan":
            if STATE.get("status") == "running":
                return self.send_json({"error":"A scan is already running"},409)
            try:
                length = int(self.headers.get("Content-Length","0"))
                raw = self.rfile.read(length)
                req = json.loads(raw.decode("utf-8"))
                target = Path(req.get("target","")).resolve()
                upload_root = UPLOAD_DIR.resolve()
                mode = str(req.get("mode","/apk360"))
                target_id=str(req.get("targetId") or "")
                rec_for_target=load_target(target_id) if target_id else None
                retained=""
                if rec_for_target:
                    retained=(rec_for_target.get("storage") or {}).get("apk","")
                retained_path=Path(retained).resolve() if retained else None
                allowed_target=target.is_relative_to(upload_root) or bool(retained_path and target == retained_path and retained_path.exists())
                if not allowed_target:
                    return self.send_json({"error":"Invalid target location"},400)
                checks=[str(x) for x in (req.get("checks") or [])]
                if not target_id:
                    rec=register_target(target,target.name);target_id=rec["id"]
                allowed_checks={x["id"] for x in catalog()["apkPlan"]}
                checks=[x for x in checks if x in allowed_checks]
                if not checks:
                    return self.send_json({"error":"Select at least one target check"},400)
                valid = {x[0] for x in APK_MODES}
                if mode not in valid:
                    return self.send_json({"error":"Invalid APK mode"},400)
                with STATE_LOCK:
                    STATE["log"] = []
                th = threading.Thread(
                    target=scan_worker,
                    args=(target,target_id,mode,checks,bool(req.get("decompile") or ("decompile" in checks)),bool(req.get("keepDecompiled")),bool(req.get("cleanup"))),
                    daemon=True,
                )
                th.start()
                return self.send_json({"ok":True})
            except Exception as exc:
                return self.send_json({"error":str(exc)},500)

        if path == "/api/frida/start":
            try:
                if frida_state_copy().get("status")=="running":
                    return self.send_json({"error":"Frida observation already running"},409)
                if not FRIDA_RUNNER.exists():
                    return self.send_json({"error":"frida_runtime.py is missing"},500)
                length=int(self.headers.get("Content-Length","0"))
                req=json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                if not bool(req.get("authorized")):
                    return self.send_json({"error":"Authorization acknowledgement is required."},400)
                tid=str(req.get("targetId") or STATE.get("targetId") or "")
                package=str(req.get("package") or "").strip()
                mode=str(req.get("mode") or "gadget")
                duration=int(req.get("duration") or 120)
                probes=[str(x) for x in (req.get("probes") or [])]
                rec=load_target(tid) if tid else None
                if not rec:return self.send_json({"error":"Target not found"},404)
                expected=(rec.get("apk") or {}).get("package","")
                if expected and package!=expected:
                    return self.send_json({"error":"Frida package must match the selected target package: "+expected},400)
                fc=frida_catalog()
                valid_modes={x["id"] for x in fc.get("modes",[]) if x["id"] in {"root-server","gadget"}}
                valid_probes={x["id"] for x in fc.get("probes",[])}
                if mode not in valid_modes:return self.send_json({"error":"Invalid Frida mode"},400)
                probes=[x for x in probes if x in valid_probes]
                if not probes:return self.send_json({"error":"Select at least one safe Frida probe"},400)
                threading.Thread(target=frida_worker,args=(package,mode,probes,duration,tid),daemon=True).start()
                return self.send_json({"ok":True,"package":package,"mode":mode})
            except Exception as exc:
                return self.send_json({"error":str(exc)},500)

        if path == "/api/frida/stop":
            global FRIDA_PROCESS
            if FRIDA_PROCESS and FRIDA_PROCESS.poll() is None:
                try:
                    FRIDA_PROCESS.terminate()
                    time.sleep(.2)
                    if FRIDA_PROCESS.poll() is None:FRIDA_PROCESS.kill()
                    set_frida_state(status="stopped",message="Stopped by user",finished=time.time())
                except Exception as exc:return self.send_json({"error":str(exc)},500)
            return self.send_json({"ok":True})

        if path == "/api/runtime/start":
            try:
                if runtime_state_copy().get("status")=="running":
                    return self.send_json({"error":"Realtime test already running"},409)
                if not shutil.which("adb"):
                    return self.send_json({"error":"ADB is not available. Static /payment /subscribes /verify /callback /fallback /recheck views still work."},400)
                length=int(self.headers.get("Content-Length","0"))
                req=json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                tid=str(req.get("targetId") or STATE.get("targetId") or "")
                package=str(req.get("package") or "").strip()
                duration=int(req.get("duration") or 120)
                rec=load_target(tid) if tid else None
                expected=(rec.get("apk") or {}).get("package","") if rec else ""
                if not rec:return self.send_json({"error":"Target not found"},404)
                if expected and package!=expected:
                    return self.send_json({"error":"Runtime package must match the selected target package: "+expected},400)
                if not package:return self.send_json({"error":"Package name unavailable; run manifest/APK analysis first."},400)
                threading.Thread(target=runtime_worker,args=(package,duration,tid),daemon=True).start()
                return self.send_json({"ok":True,"package":package})
            except Exception as exc:
                return self.send_json({"error":str(exc)},500)

        if path == "/api/runtime/stop":
            global RUNTIME_PROCESS
            if RUNTIME_PROCESS and RUNTIME_PROCESS.poll() is None:
                try:
                    RUNTIME_PROCESS.terminate()
                    time.sleep(.2)
                    if RUNTIME_PROCESS.poll() is None:RUNTIME_PROCESS.kill()
                    set_runtime_state(status="stopped",message="Stopped by user",finished=time.time())
                except Exception as exc:return self.send_json({"error":str(exc)},500)
            return self.send_json({"ok":True})

        if path == "/api/reader/remove":
            try:
                length=int(self.headers.get("Content-Length","0"))
                req=json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                tid=str(req.get("targetId") or STATE.get("targetId") or "")
                if not tid or not load_target(tid):
                    return self.send_json({"error":"Target not found"},404)
                result=remove_generated_code(tid)
                working_reader=ROOT/"android-code-reader.json"
                if working_reader.exists():
                    try:
                        wr=json.loads(working_reader.read_text(encoding="utf-8-sig"))
                        selected=load_target(tid) or {}
                        if (wr.get("summary") or {}).get("sha256") == selected.get("sha256"):
                            working_reader.unlink()
                    except Exception:
                        pass
                working_src=ROOT/".lola-apk"/"decompiled"
                if working_src.exists() and STATE.get("targetId")==tid:
                    shutil.rmtree(working_src,ignore_errors=True)
                if STATE.get("targetId")==tid:
                    set_state(reader="")
                log("Removed Lola-generated reader/JADX artifacts for target "+tid)
                return self.send_json({"ok":True,**result})
            except Exception as exc:
                return self.send_json({"error":str(exc)},500)

        if path == "/api/stop":
            global PROCESS
            if PROCESS and PROCESS.poll() is None:
                try:
                    PROCESS.terminate()
                    time.sleep(.2)
                    if PROCESS.poll() is None:
                        PROCESS.kill()
                    log("Scan stopped by user")
                    set_state(status="stopped",stage="stopped")
                except Exception as exc:
                    return self.send_json({"error":str(exc)},500)
            return self.send_json({"ok":True})

        return self.send_json({"error":"Not found"},404)

def open_android_browser(url: str):
    opener = shutil.which("termux-open-url")
    if opener:
        try:
            subprocess.Popen([opener,url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
    try:
        webbrowser.open(url)
    except Exception:
        pass

def main():
    global PORT
    import argparse
    p = argparse.ArgumentParser(description="Lola Android/mobile local web UI")
    p.add_argument("--host",default=HOST)
    p.add_argument("--port",type=int,default=PORT)
    p.add_argument("--no-open",action="store_true")
    args = p.parse_args()

    if not ANALYZER.exists() or not REPORTER.exists():
        print("Missing analyze-apk.py or build-apk-report.py")
        return 1

    STATE_DIR.mkdir(parents=True,exist_ok=True)
    set_state(tools=detect_tools())
    server = ThreadingHTTPServer((args.host,args.port),Handler)
    url = f"http://{args.host}:{args.port}/"
    print("Lola Mobile APK Scanner")
    print("Listening:",url)
    print("Localhost only:", args.host in {"127.0.0.1","localhost","::1"})
    if not args.no_open:
        threading.Timer(.7, lambda: open_android_browser(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Lola Mobile")
    finally:
        server.server_close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

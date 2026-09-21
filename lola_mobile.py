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
from lola_library import catalog, register_target, set_plan, complete_scan, list_targets, load_target

ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / ".lola-mobile" / "uploads"
STATE_DIR = ROOT / ".lola-mobile"
ANALYZER = ROOT / "analyze-apk.py"
REPORTER = ROOT / "build-apk-report.py"

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
    "tools": {},
}
STATE_LOCK = threading.Lock()
PROCESS: subprocess.Popen | None = None

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
    names = ["python","java","apkanalyzer","aapt2","aapt","apksigner","keytool","jadx","apktool","termux-open-url"]
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

def scan_worker(target: Path, target_id: str, mode: str, checks: list[str], decompile: bool, keep_decompiled: bool, cleanup: bool):
    analysis = ROOT / "apk-analysis.json"
    report = ROOT / "apk-report.html"
    try:
        set_state(
            status="running", stage="validate", target=str(target), targetId=target_id, checks=checks, mode=mode,
            progress=3, started=time.time(), finished=None, exitCode=None,
            report="", analysis=str(analysis)
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
        cmd = [sys.executable, str(ANALYZER), str(target), "--output", str(analysis)]
        if decompile:
            cmd.append("--decompile")
        if keep_decompiled:
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

        if cleanup:
            tmp = ROOT / ".lola-apk" / "decompiled"
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
                log("Removed Lola temporary decompiled output")

        finished=time.time()
        try:
            analysis_data=json.loads(analysis.read_text(encoding="utf-8-sig")) if analysis.exists() else {}
        except Exception:
            analysis_data={}
        complete_scan(
            target_id, "complete", mode, checks, analysis_data,
            {"analysis":str(analysis),"report":str(report)},
            started=STATE.get("started"), finished=finished
        )
        set_state(
            status="complete", stage="complete", progress=100, finished=finished,
            exitCode=0, report=str(report)
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
  <div class="libgrid" id="commandLibrary" style="margin-top:10px"></div>
</div>

<div class="card">
  <div class="row" style="justify-content:space-between"><b>🎯 Target Library</b><button class="ghost" onclick="refreshTargets()">Refresh</button></div>
  <div class="sub">Stored details: .lola-library/targets/&lt;target-id&gt;.json</div>
  <div class="libgrid" id="targetLibrary" style="margin-top:10px"></div>
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
let LIB={commands:[],apkPlan:[]};
let selectedChecks=new Set();
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
    ['identity','manifest','permissions','components','files','risk','store_target'].forEach(x=>selectedChecks.add(x));
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
  const items=(LIB.commands||[]).filter(x=>!q||JSON.stringify(x).toLowerCase().includes(q));
  $('libraryCount').textContent=items.length+' commands/functions';
  items.slice(0,120).forEach(x=>{
    const d=document.createElement('div');d.className='libitem';
    d.innerHTML='<b>'+x.label+' <span class="sub">'+x.id+'</span></b>'+
      '<div>'+x.purpose+'</div>'+
      '<div class="sub">'+x.group+' · cost '+x.cost+' · tools '+((x.tools||[]).join(', ')||'none')+' · outputs '+((x.outputs||[]).join(', ')||'none')+'</div>';
    if(x.id.startsWith('/apk')){
      d.onclick=()=>{selectedMode=x.id;renderModes();window.scrollTo({top:0,behavior:'smooth'})};
      d.style.cursor='pointer';
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
  alert('Loaded library plan for '+(j.name||id)+'\\nSHA-256: '+(j.sha256||''));
}
async function initLibrary(){
  try{
    const r=await fetch('/api/library',{cache:'no-store'});LIB=await r.json();
    applyPreset('recommended');renderCommandLibrary();refreshTargets();
  }catch{}
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
    if(s.status==='complete'&&lastStatus!=='complete'&&$('autoReport').checked&&!opened){opened=true;setTimeout(openReport,500)}
    lastStatus=s.status;
  }catch{}
  setTimeout(poll,700);
}
renderModes();initLibrary();poll();
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
                dest = UPLOAD_DIR / name
                remaining = size
                with dest.open("wb") as f:
                    while remaining:
                        chunk = self.rfile.read(min(1024*1024, remaining))
                        if not chunk:
                            break
                        f.write(chunk); remaining -= len(chunk)
                if remaining != 0:
                    dest.unlink(missing_ok=True)
                    return self.send_json({"error":"Upload incomplete"},400)
                rec=register_target(dest, name)
                log(f"APK uploaded: {name} · library {rec['id']}")
                set_state(target=str(dest), targetId=rec["id"], checks=rec.get("lastPlan",[]), status="idle", stage="uploaded", progress=0)
                return self.send_json({"ok":True,"name":name,"path":str(dest),"targetId":rec["id"],"sha256":rec["sha256"],"lastPlan":rec.get("lastPlan",[])})
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
                if not target.is_relative_to(upload_root):
                    return self.send_json({"error":"Invalid target location"},400)
                mode = str(req.get("mode","/apk360"))
                target_id=str(req.get("targetId") or "")
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

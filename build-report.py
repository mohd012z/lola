#!/usr/bin/env python3
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

SEV_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}

def normalize(result):
    extra = result.get("extra") or {}
    start = result.get("start") or {}
    end = result.get("end") or {}
    metadata = extra.get("metadata") or {}
    category = str(metadata.get("category") or "other")
    surface = str(metadata.get("surface") or category)
    return {
        "rule": result.get("check_id") or "unknown-rule",
        "severity": str(extra.get("severity") or "INFO").upper(),
        "message": extra.get("message") or "",
        "path": result.get("path") or "",
        "line": start.get("line") or 0,
        "col": start.get("col") or 0,
        "endLine": end.get("line") or 0,
        "endCol": end.get("col") or 0,
        "category": category,
        "surface": surface,
        "cwe": metadata.get("cwe") or "",
        "confidence": metadata.get("confidence") or "",
        "lines": (extra.get("lines") or "").strip(),
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="semgrep-results.json")
    p.add_argument("--output", default="semgrep-report.html")
    p.add_argument("--target", default="")
    p.add_argument("--manifest", default="target-manifest.json")
    p.add_argument("--urls", default="url-report.json")
    p.add_argument("--modes", default="scan-modes.json")
    p.add_argument("--mode", default="/360")
    args = p.parse_args()

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"Input not found: {src}")

    raw = json.loads(src.read_text(encoding="utf-8"))
    findings = [normalize(r) for r in raw.get("results", [])]
    findings.sort(key=lambda x: (SEV_ORDER.get(x["severity"], 9), x["surface"], x["path"], x["line"]))

    target_files = []
    manifest_path = Path(args.manifest)
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            target_files = manifest.get("files", []) or []
        except Exception:
            target_files = []

    def finding_count_for(full_path):
        mp = str(full_path or "").replace("\\", "/").lower()
        count = 0
        for item in findings:
            fp = str(item.get("path") or "").replace("\\", "/").lower()
            if fp and (mp.endswith(fp) or fp.endswith(mp)):
                count += 1
        return count

    for item in target_files:
        item["findingCount"] = finding_count_for(item.get("path"))

    url_data = {"probeEnabled": False, "urlCount": 0, "publicCount": 0, "nonPublicCount": 0, "urls": []}
    url_path = Path(args.urls)
    if url_path.exists():
        try:
            url_data = json.loads(url_path.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    mode_data = {"stepview": {}, "protocol": {}, "hidden": {}, "360": {}}
    mode_path = Path(args.modes)
    if mode_path.exists():
        try:
            mode_data = json.loads(mode_path.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    sev = Counter(x["severity"] for x in findings)
    cats = Counter(x["category"] for x in findings)
    surfaces = Counter(x["surface"] for x in findings)
    rules = Counter(x["rule"] for x in findings)
    files = Counter(x["path"] for x in findings if x["path"])

    surface_severity = defaultdict(lambda: {"ERROR": 0, "WARNING": 0, "INFO": 0})
    for x in findings:
        surface_severity[x["surface"]][x["severity"]] = surface_severity[x["surface"]].get(x["severity"], 0) + 1

    payload = {
        "target": args.target,
        "total": len(findings),
        "counts": {
            "ERROR": sev.get("ERROR", 0),
            "WARNING": sev.get("WARNING", 0),
            "INFO": sev.get("INFO", 0),
        },
        "affectedFiles": len(files),
        "categories": dict(cats),
        "surfaces": dict(surfaces),
        "surfaceSeverity": dict(surface_severity),
        "topRules": rules.most_common(12),
        "topFiles": files.most_common(12),
        "targetFiles": target_files,
        "urlData": url_data,
        "modeData": mode_data,
        "initialMode": args.mode,
        "findings": findings,
    }

    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")

    page = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codex Security Deep Surface Report</title>
<style>
:root{color-scheme:dark;--bg:#08101d;--panel:#111a2d;--panel2:#16213a;--panel3:#0d1527;--text:#edf3ff;--muted:#98a9c9;--line:#253657;--error:#ff667f;--warn:#ffc35d;--info:#65aaff;--ok:#55d7a6;--accent:#8a7cff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#152443 0,#0b1426 34%,#08101d 70%);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1500px;margin:auto;padding:24px}.hero{display:flex;gap:18px;justify-content:space-between;align-items:flex-start;margin-bottom:18px}.hero h1{margin:0 0 5px;font-size:29px}.sub{color:var(--muted);word-break:break-all}
.grid{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:12px}.card{background:rgba(17,26,45,.97);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:0 12px 35px #0003}.metric{font-size:30px;font-weight:800}.label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.09em}.error .metric{color:var(--error)}.warning .metric{color:var(--warn)}.info .metric{color:var(--info)}
.modebar{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.modebtn{width:auto;background:#101c33;color:var(--text);border:1px solid var(--line);border-radius:999px;padding:9px 13px;cursor:pointer;font-weight:700}.modebtn.active{outline:2px solid var(--accent);background:#1b2a49}.modepanel{display:none}.modepanel.active{display:block}.timeline{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.phase{background:#0b1426;border:1px solid var(--line);border-radius:13px;padding:13px}.phase h3{margin:0 0 9px}.phase-row{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid #1c2c48}.phase-row:last-child{border-bottom:0}.phase-row span:first-child{color:var(--muted)}.mode-list{display:grid;gap:8px}.mode-item{background:#0b1426;border:1px solid var(--line);border-radius:11px;padding:11px;word-break:break-word}.section{margin-top:16px}.section-head{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:10px}.section h2{font-size:17px;margin:0}
.surface-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}.surface{cursor:pointer;background:var(--panel3);border:1px solid var(--line);border-radius:13px;padding:13px;transition:.15s}.surface:hover{transform:translateY(-1px);border-color:#536d9f}.surface.active{outline:2px solid var(--accent)}.surface-top{display:flex;justify-content:space-between;gap:8px}.surface-name{font-weight:750}.surface-count{font-size:22px;font-weight:850}.mini{display:flex;gap:7px;margin-top:7px;font-size:11px;color:var(--muted)}.dotE{color:var(--error)}.dotW{color:var(--warn)}.dotI{color:var(--info)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}.bars{display:grid;gap:9px}.bar-row{display:grid;grid-template-columns:minmax(120px,220px) 1fr 46px;gap:10px;align-items:center}.bar-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.bar-bg{height:10px;background:#091223;border:1px solid #22304e;border-radius:99px;overflow:hidden}.bar-fill{height:100%;background:linear-gradient(90deg,#628eff,#9674ff);border-radius:inherit}
.controls{display:grid;grid-template-columns:minmax(240px,1.5fr) repeat(5,minmax(130px,1fr));gap:9px;margin-top:16px}.controls input,.controls select{width:100%;background:#0b1426;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px 11px}
.findings{display:grid;gap:10px}.finding{background:var(--panel);border:1px solid var(--line);border-left-width:4px;border-radius:13px;padding:14px}.finding.ERROR{border-left-color:var(--error)}.finding.WARNING{border-left-color:var(--warn)}.finding.INFO{border-left-color:var(--info)}
.row{display:flex;gap:12px;align-items:flex-start;justify-content:space-between}.left{min-width:0}.msg{font-weight:750;margin-bottom:5px}.meta{color:var(--muted);font-size:12px;word-break:break-all}.pill{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:99px;padding:3px 8px;font-size:11px;margin:0 0 5px 5px}.sev.ERROR{color:var(--error)}.sev.WARNING{color:var(--warn)}.sev.INFO{color:var(--info)}
details{margin-top:10px}summary{cursor:pointer;color:#bfd1ff}.detail-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin-top:10px}.detail{background:#0b1426;border:1px solid #22304e;border-radius:9px;padding:9px;min-width:0;overflow-wrap:anywhere}.detail b{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;margin-bottom:3px}pre{white-space:pre-wrap;overflow:auto;background:#070d19;border:1px solid #22304e;border-radius:9px;padding:11px;color:#dce7ff}
.note{margin-top:12px;padding:11px 13px;border-radius:11px;background:#0c172b;border:1px solid #233a63;color:#b9c9e7}.url-summary{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:9px;margin-bottom:10px}.url-list{display:grid;gap:9px}.url-card{background:#0b1426;border:1px solid var(--line);border-radius:12px;padding:12px}.url-main{display:grid;grid-template-columns:minmax(250px,1fr) 90px 120px 120px;gap:10px;align-items:start}.url-src,.url-final{word-break:break-all}.url-arrow{color:var(--muted);margin:5px 0}.status-ok{color:var(--ok)}.status-warn{color:var(--warn)}.status-bad{color:var(--error)}.manifest-tools{display:flex;gap:10px;align-items:center;margin-bottom:10px}.manifest-tools input{flex:1;background:#0b1426;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px 11px}.manifest{max-height:460px;overflow:auto;border:1px solid var(--line);border-radius:12px}.mf{display:grid;grid-template-columns:minmax(280px,1fr) 90px 90px 110px minmax(180px,.7fr);gap:10px;padding:10px 12px;border-bottom:1px solid #1d2d4b;align-items:center}.mf:last-child{border-bottom:0}.mfpath{word-break:break-all}.mf small{color:var(--muted)}.hash{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;word-break:break-all;color:#b8caef}.empty{padding:34px;text-align:center;color:var(--muted)}.footer{color:var(--muted);font-size:12px;margin:18px 0}
@media(max-width:1100px){.controls{grid-template-columns:1fr 1fr 1fr}.detail-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.two,.timeline{grid-template-columns:1fr}.hero{display:block}.url-summary{grid-template-columns:repeat(2,1fr)}.url-main{grid-template-columns:1fr 90px}}
@media(max-width:600px){.wrap{padding:13px}.grid,.controls,.detail-grid{grid-template-columns:1fr}.row{display:block}.bar-row{grid-template-columns:100px 1fr 38px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div><h1>🛡️ Codex Security — Deep Surface Report</h1><div class="sub" id="target"></div></div>
    <div class="sub">Paths • routes • network • client IP • crypto • TLS • database</div>
  </div>

  <div class="grid">
    <div class="card"><div class="label">Total findings</div><div class="metric" id="total">0</div></div>
    <div class="card error"><div class="label">Errors</div><div class="metric" id="errors">0</div></div>
    <div class="card warning"><div class="label">Warnings</div><div class="metric" id="warnings">0</div></div>
    <div class="card info"><div class="label">Info / inventory</div><div class="metric" id="infos">0</div></div>
    <div class="card"><div class="label">Affected files</div><div class="metric" id="files">0</div></div>
  </div>

  <div class="modebar" id="modebar">
    <button class="modebtn" data-mode="/stepview">/stepview</button>
    <button class="modebtn" data-mode="/protocol">/protocol</button>
    <button class="modebtn" data-mode="/hidden">/hidden</button>
    <button class="modebtn" data-mode="/360">/360</button>
  </div>

  <div class="section card modepanel" id="stepviewPanel">
    <div class="section-head"><h2>/stepview — Before / During / After</h2><span class="sub">Retrospective scan flow</span></div>
    <div class="timeline" id="stepTimeline"></div>
  </div>

  <div class="section card modepanel" id="protocolPanel">
    <div class="section-head"><h2>/protocol — Protocol map</h2><span class="sub">Transport, messaging and API protocols</span></div>
    <div class="surface-grid" id="protocolCards"></div>
    <div class="mode-list" id="protocolEvidence" style="margin-top:10px"></div>
  </div>

  <div class="section card modepanel" id="hiddenPanel">
    <div class="section-head"><h2>/hidden — Hidden & sensitive surfaces</h2><span class="sub">Dot paths, hidden attributes, hidden UI, sensitive configs</span></div>
    <div class="url-summary" id="hiddenSummary"></div>
    <div class="mode-list" id="hiddenEvidence"></div>
  </div>

  <div class="section card modepanel" id="view360Panel">
    <div class="section-head"><h2>/360 — Full scan view</h2><span class="sub">All discovered surfaces combined</span></div>
    <div class="url-summary" id="view360Summary"></div>
    <div class="note">360 view combines file/path inventory, URLs, IP/network, device/privacy/account, encryption/TLS, protocols, hidden surfaces, database/routes and security findings.</div>
  </div>

  <div class="section card">
    <div class="section-head"><h2>Attack-surface map</h2><span class="sub">Click a surface to filter findings</span></div>
    <div class="surface-grid" id="surfaces"></div>
    <div class="note">Client-IP findings show where the application reads peer/proxy IP information such as <b>req.ip</b>, <b>X-Forwarded-For</b>, <b>X-Real-IP</b>, or similar headers. They do not independently discover a person's physical location. Forwarded headers are trustworthy only when the proxy chain is correctly controlled/configured.</div>
  </div>

  <div class="section card">
    <div class="section-head"><h2>Real URL map</h2><span class="sub" id="urlMode"></span></div>
    <div class="url-summary">
      <div class="detail"><b>URLs found</b><span id="urlCount">0</span></div>
      <div class="detail"><b>Public destinations</b><span id="urlPublic">0</span></div>
      <div class="detail"><b>Private / unresolved</b><span id="urlNonPublic">0</span></div>
      <div class="detail"><b>Live verified</b><span id="urlVerified">0</span></div>
    </div>
    <div class="manifest-tools"><input id="urlSearch" placeholder="Search source URL, final URL, host, IP, source file..."></div>
    <div class="url-list" id="urlList"></div>
    <div class="note"><b>Source URL</b> is what appears in code/config. With <b>-ResolveUrls</b>, public destinations are requested and the report also shows the <b>final URL</b> after redirects, HTTP status, resolved public IPs, redirect chain, and TLS version/cipher. Private/local/reserved destinations are never live-probed.</div>
  </div>

  <div class="section card">
    <div class="section-head"><h2>Device & privacy map</h2><span class="sub">Browser • Android • iOS • desktop • cross-platform</span></div>
    <div class="surface-grid" id="deviceSurfaces"></div>
    <div class="note">This section maps <b>code that reads or requests device information/capabilities</b> such as user agent, hardware characteristics, camera/microphone, geolocation, permissions, local network interfaces, Android/iOS identifiers and cross-platform device plugins. It does not collect your actual current device values by itself.</div>
  </div>

  <div class="section card">
    <div class="section-head"><h2>Account & personal-data map</h2><span class="sub">Authentication • contacts • calendar • files • biometrics</span></div>
    <div class="surface-grid" id="accountSurfaces"></div>
    <div class="note">This map shows where source code touches account/authentication or personal-data APIs. It does not enumerate a user's real accounts, passwords, contacts, or files. Browser and OS permission/consent boundaries still apply at runtime.</div>
  </div>

  <div class="section card">
    <div class="section-head"><h2>Target file manifest</h2><span class="sub" id="manifestCount"></span></div>
    <div class="manifest-tools"><input id="manifestSearch" placeholder="Search every scanned path, extension, hash..."></div>
    <div class="manifest" id="manifest"></div>
    <div class="note">The manifest records candidate source/config files with full path, size, modified time, SHA-256, and how many findings map to that file. The complete machine-readable list is also saved as <b>target-manifest.json</b>.</div>
  </div>

  <div class="two section">
    <div class="card">
      <div class="section-head"><h2>Top triggered rules</h2><span class="sub">Frequency</span></div>
      <div class="bars" id="ruleBars"></div>
    </div>
    <div class="card">
      <div class="section-head"><h2>Most affected files</h2><span class="sub">Findings per file</span></div>
      <div class="bars" id="fileBars"></div>
    </div>
  </div>

  <div class="controls">
    <input id="search" placeholder="Search path, IP, URL, crypto, rule, message, CWE...">
    <select id="severity"><option value="">All severities</option><option>ERROR</option><option>WARNING</option><option>INFO</option></select>
    <select id="surface"><option value="">All surfaces</option></select>
    <select id="category"><option value="">All categories</option></select>
    <select id="file"><option value="">All files</option></select>
    <select id="rule"><option value="">All rules</option></select>
  </div>

  <div class="section">
    <div class="section-head"><h2>Detailed evidence</h2><span class="sub" id="shown"></span></div>
    <div class="findings" id="findings"></div>
  </div>

  <div class="footer">Static analysis provides evidence and review signals. Confirm findings in application context before deciding severity or remediation.</div>
</div>

<script id="semgrep-data" type="application/json">__DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('semgrep-data').textContent);
const $=id=>document.getElementById(id);
const MODEDATA=DATA.modeData||{stepview:{},protocol:{},hidden:{},360:{}};

function miniMetric(parent,label,value){
  const d=document.createElement('div');d.className='detail';
  const b=document.createElement('b');b.textContent=label;
  const s=document.createElement('span');s.textContent=String(value??'-');
  d.append(b,s);parent.appendChild(d);
}
function renderModes(){
  const tl=$('stepTimeline');tl.replaceChildren();
  for(const key of ['before','during','after']){
    const p=MODEDATA.stepview?.[key]||{title:key,items:[]};
    const box=document.createElement('div');box.className='phase';
    const h=document.createElement('h3');h.textContent=(key==='before'?'⏮️ ':key==='during'?'⏳ ':'✅ ')+(p.title||key);box.appendChild(h);
    (p.items||[]).forEach(it=>{const r=document.createElement('div');r.className='phase-row';const a=document.createElement('span');a.textContent=it.label;const b=document.createElement('strong');b.textContent=String(it.value??'-');r.append(a,b);box.appendChild(r)});
    tl.appendChild(box);
  }

  const pc=$('protocolCards');pc.replaceChildren();
  Object.entries(MODEDATA.protocol?.counts||{}).sort((a,b)=>b[1]-a[1]).forEach(([name,count])=>{
    const d=document.createElement('div');d.className='surface';const t=document.createElement('div');t.className='surface-top';
    const n=document.createElement('div');n.className='surface-name';n.textContent='🔌 '+name;const v=document.createElement('div');v.className='surface-count';v.textContent=count;t.append(n,v);d.appendChild(t);pc.appendChild(d);
  });
  if(!pc.children.length) pc.innerHTML='<div class="empty">No protocol surfaces detected.</div>';

  const pe=$('protocolEvidence');pe.replaceChildren();
  (MODEDATA.protocol?.findings||[]).slice(0,80).forEach(x=>{const d=document.createElement('div');d.className='mode-item';d.textContent=(x.surface||x.category||'protocol')+' • '+(x.path||'')+(x.line?':'+x.line:'')+' — '+(x.message||x.rule||'');pe.appendChild(d)});

  const hs=$('hiddenSummary');hs.replaceChildren();
  const hc=MODEDATA.hidden?.counts||{};
  miniMetric(hs,'Hidden/sensitive files',hc.files||0);miniMetric(hs,'Hidden findings',hc.findings||0);miniMetric(hs,'Dot paths',hc.dotPaths||0);miniMetric(hs,'Sensitive config',hc.sensitiveConfig||0);
  const he=$('hiddenEvidence');he.replaceChildren();
  (MODEDATA.hidden?.files||[]).slice(0,100).forEach(x=>{const d=document.createElement('div');d.className='mode-item';d.textContent=(x.reason||'hidden')+' • '+(x.path||x.name||'');he.appendChild(d)});
  (MODEDATA.hidden?.findings||[]).slice(0,100).forEach(x=>{const d=document.createElement('div');d.className='mode-item';d.textContent=(x.surface||'hidden')+' • '+(x.path||'')+(x.line?':'+x.line:'')+' — '+(x.message||x.rule||'');he.appendChild(d)});

  const vs=$('view360Summary');vs.replaceChildren();
  const sm=MODEDATA['360']?.summary||{};
  miniMetric(vs,'Files',sm.files||0);miniMetric(vs,'URLs',sm.urls||0);miniMetric(vs,'Findings',sm.findings||0);miniMetric(vs,'Errors',sm.errors||0);
  miniMetric(vs,'Warnings',sm.warnings||0);miniMetric(vs,'Protocols',sm.protocolSurfaces||0);miniMetric(vs,'Hidden files',sm.hiddenFiles||0);miniMetric(vs,'Info',sm.info||0);
}
function setMode(mode){
  const normalized=mode.startsWith('/')?mode:'/'+mode;
  document.querySelectorAll('.modebtn').forEach(b=>b.classList.toggle('active',b.dataset.mode===normalized));
  const map={'/stepview':'stepviewPanel','/protocol':'protocolPanel','/hidden':'hiddenPanel','/360':'view360Panel'};
  document.querySelectorAll('.modepanel').forEach(p=>p.classList.remove('active'));
  const panel=$(map[normalized]||'view360Panel');if(panel)panel.classList.add('active');
  if(normalized==='/protocol'){$('category').value='protocol';render()}
  else if(normalized==='/hidden'){$('category').value='hidden';render()}
  else if(normalized==='/360'){$('category').value='';$('surface').value='';$('search').value='';render()}
  panel?.scrollIntoView({behavior:'smooth',block:'start'});
}
const ICONS={
  filesystem:'🗂️','http-files':'📦',uploads:'⬆️','http-routes':'🛣️','browser-navigation':'🧭',
  'network-addresses':'🌐','private-network':'🏠','client-ip':'🛰️','proxy-trust':'🛡️',
  listeners:'📡',dns:'🔎',encryption:'🔐',webcrypto:'🔒','key-derivation':'🗝️',random:'🎲',
  signatures:'✍️',tls:'🔏',database:'🗄️',inventory:'📋',security:'⚠️',secrets:'🔑',storage:'💾',
  'device-identity':'🧩','device-fingerprinting':'🕵️','device-media':'🎥','device-location':'📍',
  'device-permissions':'✅','device-clipboard':'📋','device-power':'🔋','device-network':'📶',
  'device-storage':'💽','device-local-network':'🛜','device-host':'🖥️','android-device':'🤖',
  'ios-device':'','device-identifiers':'🪪','device-capabilities':'🧰','device-bridge':'🌉',
  'device-files':'🗃️','account-auth':'👤','personal-data':'👥','device-biometric':'🔐','device-notifications':'🔔'
};
const icon=s=>ICONS[s]||'•';
$('target').textContent=DATA.target ? 'Target: '+DATA.target : 'Target not recorded';
$('total').textContent=DATA.total;$('errors').textContent=DATA.counts.ERROR||0;$('warnings').textContent=DATA.counts.WARNING||0;$('infos').textContent=DATA.counts.INFO||0;$('files').textContent=DATA.affectedFiles||0;

function fillSelect(el,values){values.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;el.appendChild(o)})}
fillSelect($('surface'),Object.keys(DATA.surfaces||{}).sort());
fillSelect($('category'),Object.keys(DATA.categories||{}).sort());
fillSelect($('file'),[...new Set(DATA.findings.map(x=>x.path).filter(Boolean))].sort());
fillSelect($('rule'),[...new Set(DATA.findings.map(x=>x.rule))].sort());

Object.entries(DATA.surfaces||{}).sort((a,b)=>b[1]-a[1]).forEach(([name,count])=>{
  const s=DATA.surfaceSeverity[name]||{};const card=document.createElement('div');card.className='surface';card.dataset.surface=name;
  const top=document.createElement('div');top.className='surface-top';
  const n=document.createElement('div');n.className='surface-name';n.textContent=icon(name)+' '+name;
  const c=document.createElement('div');c.className='surface-count';c.textContent=count;top.append(n,c);card.appendChild(top);
  const mini=document.createElement('div');mini.className='mini';
  mini.innerHTML='<span class="dotE">E '+(s.ERROR||0)+'</span><span class="dotW">W '+(s.WARNING||0)+'</span><span class="dotI">I '+(s.INFO||0)+'</span>';
  card.appendChild(mini);card.onclick=()=>{const sel=$('surface');sel.value=(sel.value===name?'':name);document.querySelectorAll('.surface').forEach(x=>x.classList.toggle('active',x.dataset.surface===sel.value));render()};
  $('surfaces').appendChild(card);
});
if(!Object.keys(DATA.surfaces||{}).length){$('surfaces').innerHTML='<div class="empty">No surface findings</div>'}

const deviceNames=new Set([
  'device-identity','device-fingerprinting','device-media','device-location','device-permissions',
  'device-clipboard','device-power','device-network','device-storage','device-local-network',
  'device-host','android-device','ios-device','device-identifiers','device-capabilities','device-bridge',
  'device-files','account-auth','personal-data','device-biometric','device-notifications'
]);
Object.entries(DATA.surfaces||{}).filter(([name])=>deviceNames.has(name)).sort((a,b)=>b[1]-a[1]).forEach(([name,count])=>{
  const s=DATA.surfaceSeverity[name]||{};const card=document.createElement('div');card.className='surface';card.dataset.surface=name;
  const top=document.createElement('div');top.className='surface-top';
  const n=document.createElement('div');n.className='surface-name';n.textContent=icon(name)+' '+name;
  const ct=document.createElement('div');ct.className='surface-count';ct.textContent=count;top.append(n,ct);card.appendChild(top);
  const mini=document.createElement('div');mini.className='mini';mini.innerHTML='<span class="dotE">E '+(s.ERROR||0)+'</span><span class="dotW">W '+(s.WARNING||0)+'</span><span class="dotI">I '+(s.INFO||0)+'</span>';card.appendChild(mini);
  card.onclick=()=>{const sel=$('surface');sel.value=(sel.value===name?'':name);document.querySelectorAll('.surface').forEach(x=>x.classList.toggle('active',x.dataset.surface===sel.value));render()};
  $('deviceSurfaces').appendChild(card);
});
if(!$('deviceSurfaces').children.length){$('deviceSurfaces').innerHTML='<div class="empty">No device/privacy APIs detected in this scan.</div>'}

const accountNames=new Set(['account-auth','personal-data','device-files','device-biometric','device-notifications','device-media']);
Object.entries(DATA.surfaces||{}).filter(([name])=>accountNames.has(name)).sort((a,b)=>b[1]-a[1]).forEach(([name,count])=>{
  const s=DATA.surfaceSeverity[name]||{};const card=document.createElement('div');card.className='surface';card.dataset.surface=name;
  const top=document.createElement('div');top.className='surface-top';
  const n=document.createElement('div');n.className='surface-name';n.textContent=icon(name)+' '+name;
  const ct=document.createElement('div');ct.className='surface-count';ct.textContent=count;top.append(n,ct);card.appendChild(top);
  const mini=document.createElement('div');mini.className='mini';mini.innerHTML='<span class="dotE">E '+(s.ERROR||0)+'</span><span class="dotW">W '+(s.WARNING||0)+'</span><span class="dotI">I '+(s.INFO||0)+'</span>';card.appendChild(mini);
  card.onclick=()=>{const sel=$('surface');sel.value=(sel.value===name?'':name);document.querySelectorAll('.surface').forEach(x=>x.classList.toggle('active',x.dataset.surface===sel.value));render()};
  $('accountSurfaces').appendChild(card);
});
if(!$('accountSurfaces').children.length){$('accountSurfaces').innerHTML='<div class="empty">No account/personal-data APIs detected in this scan.</div>'}

function renderBars(rootId,items){
  const root=$(rootId),max=Math.max(1,...items.map(x=>x[1]));
  if(!items.length){root.innerHTML='<div class="empty">No data</div>';return}
  items.forEach(([name,count])=>{const row=document.createElement('div');row.className='bar-row';const n=document.createElement('div');n.className='bar-name';n.textContent=name;n.title=name;const bg=document.createElement('div');bg.className='bar-bg';const fill=document.createElement('div');fill.className='bar-fill';fill.style.width=(count/max*100)+'%';bg.appendChild(fill);const c=document.createElement('div');c.textContent=count;row.append(n,bg,c);root.appendChild(row)})
}
renderBars('ruleBars',DATA.topRules||[]);renderBars('fileBars',DATA.topFiles||[]);

const URLDATA=DATA.urlData||{urls:[]};
$('urlCount').textContent=URLDATA.urlCount||0;
$('urlPublic').textContent=URLDATA.publicCount||0;
$('urlNonPublic').textContent=URLDATA.nonPublicCount||0;
$('urlVerified').textContent=(URLDATA.urls||[]).filter(x=>x.probed).length;
$('urlMode').textContent=URLDATA.probeEnabled?'Live public URL verification enabled':'Static URL inventory — rerun with -ResolveUrls for final URLs';

function renderUrls(){
  const q=$('urlSearch').value.trim().toLowerCase();
  const rows=(URLDATA.urls||[]).filter(x=>[
    x.sourceUrl,x.finalUrl,x.host,(x.resolvedIps||[]).join(' '),
    ...(x.occurrences||[]).map(o=>(o.path||'')+' '+(o.line||''))
  ].join(' ').toLowerCase().includes(q));
  const root=$('urlList');root.replaceChildren();
  if(!rows.length){root.innerHTML='<div class="empty">No URLs match.</div>';return}
  rows.forEach(x=>{
    const card=document.createElement('div');card.className='url-card';
    const main=document.createElement('div');main.className='url-main';
    const left=document.createElement('div');
    const src=document.createElement('div');src.className='url-src';src.textContent=x.sourceUrl||'';left.appendChild(src);
    const arrow=document.createElement('div');arrow.className='url-arrow';arrow.textContent=x.probed?'↓ final destination':'↓ not live-probed';left.appendChild(arrow);
    const fin=document.createElement('div');fin.className='url-final';fin.textContent=x.finalUrl||'(same/unknown until live verification)';left.appendChild(fin);
    const st=document.createElement('div');st.textContent=x.status||'-';st.className=x.status&&x.status<400?'status-ok':(x.status?'status-warn':'');
    const cls=document.createElement('div');cls.textContent=x.destinationClass||'-';
    const ips=document.createElement('div');ips.textContent=(x.resolvedIps||[]).join(', ')||'-';ips.className='meta';
    main.append(left,st,cls,ips);card.appendChild(main);
    const details=document.createElement('details');const sm=document.createElement('summary');sm.textContent='URL evidence / redirects / TLS';details.appendChild(sm);
    const grid=document.createElement('div');grid.className='detail-grid';
    detailBox(grid,'Host',x.host);detailBox(grid,'Scheme',x.scheme);detailBox(grid,'Port',x.port||'-');detailBox(grid,'HTTP status',x.status||'-');detailBox(grid,'Redirects',(x.redirects||[]).length);detailBox(grid,'TLS',(x.tls&&x.tls.version)?(x.tls.version+' '+(x.tls.cipher||'')):'-');
    details.appendChild(grid);
    if((x.occurrences||[]).length){const pre=document.createElement('pre');pre.textContent='Found in:\n'+x.occurrences.map(o=>(o.path||'')+':'+(o.line||'?')).join('\n');details.appendChild(pre)}
    if((x.redirects||[]).length){const pre=document.createElement('pre');pre.textContent='Redirect chain:\n'+x.redirects.map(r=>r.status+'  '+r.from+'\n  -> '+r.to).join('\n');details.appendChild(pre)}
    if(x.error){const pre=document.createElement('pre');pre.textContent='Resolver note: '+x.error;details.appendChild(pre)}
    card.appendChild(details);root.appendChild(card);
  });
}
$('urlSearch').addEventListener('input',renderUrls);renderUrls();

function fmtBytes(n){n=Number(n||0);if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KB';return (n/1048576).toFixed(1)+' MB'}
function renderManifest(){
  const q=$('manifestSearch').value.trim().toLowerCase();
  const all=(DATA.targetFiles||[]).filter(x=>[x.path,x.name,x.extension,x.sha256].join(' ').toLowerCase().includes(q));
  $('manifestCount').textContent=all.length+' of '+(DATA.targetFiles||[]).length+' files';
  const root=$('manifest');root.replaceChildren();
  if(!all.length){root.innerHTML='<div class="empty">No target paths match.</div>';return}
  all.forEach(x=>{
    const row=document.createElement('div');row.className='mf';
    const p=document.createElement('div');p.className='mfpath';p.textContent=x.path||x.name||'';row.appendChild(p);
    const e=document.createElement('div');e.textContent=x.extension||'[none]';row.appendChild(e);
    const s=document.createElement('div');s.textContent=fmtBytes(x.bytes);row.appendChild(s);
    const f=document.createElement('div');f.textContent=(x.findingCount||0)+' finding'+((x.findingCount||0)===1?'':'s');row.appendChild(f);
    const h=document.createElement('div');h.className='hash';h.textContent=x.sha256||'hash unavailable';h.title=(x.modifiedUtc?'Modified UTC: '+x.modifiedUtc:'');row.appendChild(h);
    root.appendChild(row);
  });
}
$('manifestSearch').addEventListener('input',renderManifest);renderManifest();

function addText(parent,tag,text,cls){const el=document.createElement(tag);if(cls)el.className=cls;el.textContent=text;parent.appendChild(el);return el}
function detailBox(parent,label,value){const d=document.createElement('div');d.className='detail';addText(d,'b',label);addText(d,'span',value||'-');parent.appendChild(d)}

function render(){
  const q=$('search').value.trim().toLowerCase(),sev=$('severity').value,surface=$('surface').value,cat=$('category').value,file=$('file').value,rule=$('rule').value;
  document.querySelectorAll('.surface').forEach(x=>x.classList.toggle('active',x.dataset.surface===surface));
  const rows=DATA.findings.filter(x=>{
    const hay=[x.path,x.rule,x.message,x.cwe,x.category,x.surface,x.lines,x.confidence].join(' ').toLowerCase();
    return (!q||hay.includes(q))&&(!sev||x.severity===sev)&&(!surface||x.surface===surface)&&(!cat||x.category===cat)&&(!file||x.path===file)&&(!rule||x.rule===rule);
  });
  $('shown').textContent=rows.length+' of '+DATA.findings.length;
  const root=$('findings');root.replaceChildren();
  if(!rows.length){addText(root,'div','No findings match the current filters.','empty');return}
  rows.forEach(x=>{
    const card=document.createElement('div');card.className='finding '+x.severity;
    const row=document.createElement('div');row.className='row';const left=document.createElement('div');left.className='left';
    addText(left,'div',x.message||x.rule,'msg');
    addText(left,'div',(x.path||'[unknown file]')+(x.line?':'+x.line+(x.col?':'+x.col:''):'')+'  •  '+x.rule,'meta');
    const tags=document.createElement('div');addText(tags,'span',x.severity,'pill sev '+x.severity);addText(tags,'span',icon(x.surface)+' '+x.surface,'pill');if(x.cwe)addText(tags,'span',x.cwe,'pill');row.append(left,tags);card.appendChild(row);

    const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='View exact evidence and trace metadata';details.appendChild(summary);
    const grid=document.createElement('div');grid.className='detail-grid';
    detailBox(grid,'Surface',x.surface);detailBox(grid,'Category',x.category);detailBox(grid,'Rule',x.rule);detailBox(grid,'Confidence',x.confidence);detailBox(grid,'CWE',x.cwe);detailBox(grid,'Location',x.line?('L'+x.line+':'+x.col+' → L'+x.endLine+':'+x.endCol):'-');
    details.appendChild(grid);if(x.lines){const pre=document.createElement('pre');pre.textContent=x.lines;details.appendChild(pre)}
    card.appendChild(details);root.appendChild(card);
  });
}
['search','severity','surface','category','file','rule'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',render));
document.querySelectorAll('.modebtn').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.mode)));
renderModes();
render();
setMode(DATA.initialMode||'/360');
</script>
</body>
</html>""".replace("__DATA__", data)

    Path(args.output).write_text(page, encoding="utf-8")
    print(f"Visual report written: {Path(args.output).resolve()}")

if __name__ == "__main__":
    main()

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
    p.add_argument("--code", default="code-analysis.json")
    p.add_argument("--network", default="network-analysis.json")
    p.add_argument("--preflight", default="preflight-analysis.json")
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

    code_data = {
        "summary": {}, "extraction": {}, "codesummary": {}, "codeview": {"files":[]},
        "codepassword": {"items":[]}, "codestring": {"items":[]},
        "codetransparent": {"files":[]}, "codemodification": {"items":[]},
        "codefallback": {"items":[]}, "codeurls": {"items":[]},
        "codeencryption": {"items":[]}, "hiddenmode": {"items":[]}
    }
    code_path = Path(args.code)
    if code_path.exists():
        try:
            code_data = json.loads(code_path.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    network_data = {
        "summary": {}, "trace": {"items":[]}, "route": {"items":[]},
        "map": {"nodes":[],"edges":[]}, "visible": {}, "realip": {}, "normal": {}
    }
    network_path = Path(args.network)
    if network_path.exists():
        try:
            network_data = json.loads(network_path.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    preflight_data = {
        "summary": {}, "viewextraction": {}, "viewurls": {"items":[]}, "map": {"nodes":[],"edges":[]},
        "routes": {"items":[]}, "api": {"items":[]}, "keys": {"items":[]},
        "hiddentraces": {"items":[]}, "hidemodes": {"items":[]}, "hidelog": {"items":[]},
        "ipmirror": {"items":[]}, "certs": {"items":[],"copies":[]}, "capture": {}
    }
    preflight_path = Path(args.preflight)
    if preflight_path.exists():
        try:
            preflight_data = json.loads(preflight_path.read_text(encoding="utf-8-sig"))
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
        "codeData": code_data,
        "networkData": network_data,
        "preflightData": preflight_data,
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
.modebar{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.modebtn{width:auto;background:#101c33;color:var(--text);border:1px solid var(--line);border-radius:999px;padding:9px 13px;cursor:pointer;font-weight:700}.modebtn.active{outline:2px solid var(--accent);background:#1b2a49}.modepanel{display:none}.modepanel.active{display:block}.timeline{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.phase{background:#0b1426;border:1px solid var(--line);border-radius:13px;padding:13px}.phase h3{margin:0 0 9px}.phase-row{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid #1c2c48}.phase-row:last-child{border-bottom:0}.phase-row span:first-child{color:var(--muted)}.mode-list{display:grid;gap:8px}.mode-item{background:#0b1426;border:1px solid var(--line);border-radius:11px;padding:11px;word-break:break-word}.code-toolbar{display:grid;grid-template-columns:minmax(220px,1fr) minmax(180px,320px);gap:9px;margin:10px 0}.code-toolbar input,.code-toolbar select{width:100%;background:#0b1426;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px 11px}.code-view{max-height:620px;overflow:auto;background:#070d19;border:1px solid var(--line);border-radius:12px;padding:12px}.code-view pre{margin:0;white-space:pre;overflow:auto}.code-redact{color:var(--warn);font-size:12px}.section{margin-top:16px}.section-head{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:10px}.section h2{font-size:17px;margin:0}
.surface-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}.surface{cursor:pointer;background:var(--panel3);border:1px solid var(--line);border-radius:13px;padding:13px;transition:.15s}.surface:hover{transform:translateY(-1px);border-color:#536d9f}.surface.active{outline:2px solid var(--accent)}.surface-top{display:flex;justify-content:space-between;gap:8px}.surface-name{font-weight:750}.surface-count{font-size:22px;font-weight:850}.mini{display:flex;gap:7px;margin-top:7px;font-size:11px;color:var(--muted)}.dotE{color:var(--error)}.dotW{color:var(--warn)}.dotI{color:var(--info)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}.bars{display:grid;gap:9px}.bar-row{display:grid;grid-template-columns:minmax(120px,220px) 1fr 46px;gap:10px;align-items:center}.bar-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.bar-bg{height:10px;background:#091223;border:1px solid #22304e;border-radius:99px;overflow:hidden}.bar-fill{height:100%;background:linear-gradient(90deg,#628eff,#9674ff);border-radius:inherit}
.controls{display:grid;grid-template-columns:minmax(240px,1.5fr) repeat(5,minmax(130px,1fr));gap:9px;margin-top:16px}.controls input,.controls select{width:100%;background:#0b1426;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px 11px}
.findings{display:grid;gap:10px}.finding{background:var(--panel);border:1px solid var(--line);border-left-width:4px;border-radius:13px;padding:14px}.finding.ERROR{border-left-color:var(--error)}.finding.WARNING{border-left-color:var(--warn)}.finding.INFO{border-left-color:var(--info)}
.row{display:flex;gap:12px;align-items:flex-start;justify-content:space-between}.left{min-width:0}.msg{font-weight:750;margin-bottom:5px}.meta{color:var(--muted);font-size:12px;word-break:break-all}.pill{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:99px;padding:3px 8px;font-size:11px;margin:0 0 5px 5px}.sev.ERROR{color:var(--error)}.sev.WARNING{color:var(--warn)}.sev.INFO{color:var(--info)}
details{margin-top:10px}summary{cursor:pointer;color:#bfd1ff}.detail-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin-top:10px}.detail{background:#0b1426;border:1px solid #22304e;border-radius:9px;padding:9px;min-width:0;overflow-wrap:anywhere}.detail b{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;margin-bottom:3px}pre{white-space:pre-wrap;overflow:auto;background:#070d19;border:1px solid #22304e;border-radius:9px;padding:11px;color:#dce7ff}
.note{margin-top:12px;padding:11px 13px;border-radius:11px;background:#0c172b;border:1px solid #233a63;color:#b9c9e7}.url-summary{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:9px;margin-bottom:10px}.url-list{display:grid;gap:9px}.url-card{background:#0b1426;border:1px solid var(--line);border-radius:12px;padding:12px}.url-main{display:grid;grid-template-columns:minmax(250px,1fr) 90px 120px 120px;gap:10px;align-items:start}.url-src,.url-final{word-break:break-all}.url-arrow{color:var(--muted);margin:5px 0}.status-ok{color:var(--ok)}.status-warn{color:var(--warn)}.status-bad{color:var(--error)}.manifest-tools{display:flex;gap:10px;align-items:center;margin-bottom:10px}.manifest-tools input{flex:1;background:#0b1426;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px 11px}.manifest{max-height:460px;overflow:auto;border:1px solid var(--line);border-radius:12px}.mf{display:grid;grid-template-columns:minmax(280px,1fr) 90px 90px 110px minmax(180px,.7fr);gap:10px;padding:10px 12px;border-bottom:1px solid #1d2d4b;align-items:center}.mf:last-child{border-bottom:0}.mfpath{word-break:break-all}.mf small{color:var(--muted)}.hash{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;word-break:break-all;color:#b8caef}.empty{padding:34px;text-align:center;color:var(--muted)}.footer{color:var(--muted);font-size:12px;margin:18px 0}
@media(max-width:1100px){.controls{grid-template-columns:1fr 1fr 1fr}.detail-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.two,.timeline{grid-template-columns:1fr}.hero{display:block}.url-summary{grid-template-columns:repeat(2,1fr)}.url-main{grid-template-columns:1fr 90px}}
@media(max-width:600px){.wrap{padding:13px}.grid,.controls,.detail-grid,.code-toolbar{grid-template-columns:1fr}.row{display:block}.bar-row{grid-template-columns:100px 1fr 38px}}
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
    <button class="modebtn" data-mode="/deep-dive">/deep-dive · All Details</button>
    <button class="modebtn" data-mode="/securitycheck">/securitycheck</button>
    <button class="modebtn" data-mode="/anonymus">/anonymus</button>
    <button class="modebtn" data-mode="/stepview">/stepview</button>
    <button class="modebtn" data-mode="/protocol">/protocol</button>
    <button class="modebtn" data-mode="/hidden">/hidden</button>
    <button class="modebtn" data-mode="/360">/360</button>
  </div>

  <div class="card" style="margin-top:10px">
    <div class="section-head"><h2>Pre-scan target commands</h2><span class="sub">Generated before Semgrep</span></div>
    <div class="modebar" style="margin:0">
      <button class="modebtn" data-mode="/preflight">/preflight</button>
      <button class="modebtn" data-mode="/viewextraction">/viewextraction</button>
      <button class="modebtn" data-mode="/viewurls">/viewurls</button>
      <button class="modebtn" data-mode="/map">/map</button>
      <button class="modebtn" data-mode="/routes">/routes</button>
      <button class="modebtn" data-mode="/api">/api</button>
      <button class="modebtn" data-mode="/keys">/keys</button>
      <button class="modebtn" data-mode="/hiddentraces">/hiddentraces</button>
      <button class="modebtn" data-mode="/hidemodes">/hidemodes</button>
      <button class="modebtn" data-mode="/hidelog">/hidelog</button>
      <button class="modebtn" data-mode="/ipmirror">/ipmirror</button>
      <button class="modebtn" data-mode="/certs">/certs</button>
    </div>
  </div>

  <div class="section card modepanel" id="preflightModePanel">
    <div class="section-head"><h2 id="preflightModeTitle">Pre-scan target analysis</h2><span class="sub" id="preflightModeSubtitle"></span></div>
    <div class="url-summary" id="preflightModeSummary"></div>
    <div class="mode-list" id="preflightModeList"></div>
    <div class="note" id="preflightModeNote"></div>
  </div>

  <div class="card" style="margin-top:10px">
    <div class="section-head"><h2>Network analysis commands</h2><span class="sub">Application-layer trace; no external port scan</span></div>
    <div class="modebar" style="margin:0">
      <button class="modebtn" data-mode="/deep-network">/deep-dive network</button>
      <button class="modebtn" data-mode="/trace">/trace</button>
      <button class="modebtn" data-mode="/route">/route</button>
      <button class="modebtn" data-mode="/map">/map</button>
      <button class="modebtn" data-mode="/visible">/visible</button>
      <button class="modebtn" data-mode="/realip">/realip</button>
      <button class="modebtn" data-mode="/cctv">/cctv</button>
      <button class="modebtn" data-mode="/normal">/normal</button>
    </div>
  </div>

  <div class="section card modepanel" id="networkModePanel">
    <div class="section-head"><h2 id="networkModeTitle">Network analysis</h2><span class="sub" id="networkModeSubtitle"></span></div>
    <div class="url-summary" id="networkModeSummary"></div>
    <div class="mode-list" id="networkModeList"></div>
    <div class="note" id="networkModeNote"></div>
  </div>

  <div class="card" style="margin-top:10px">
    <div class="section-head"><h2>Code analysis commands</h2><span class="sub">Source indexing uses redaction for secret-like values</span></div>
    <div class="modebar" style="margin:0">
      <button class="modebtn" data-mode="/deep-code">/deep-dive code</button>
      <button class="modebtn" data-mode="/extraction">/extraction</button>
      <button class="modebtn" data-mode="/codesummary">/codesummary</button>
      <button class="modebtn" data-mode="/codeview">/codeview</button>
      <button class="modebtn" data-mode="/codepassword">/codepassword</button>
      <button class="modebtn" data-mode="/codestring">/codestring</button>
      <button class="modebtn" data-mode="/codetransparent">/codetransparent</button>
      <button class="modebtn" data-mode="/codemodification">/codemodification</button>
      <button class="modebtn" data-mode="/codefallback">/codefallback</button>
      <button class="modebtn" data-mode="/codeurls">/codeurls</button>
      <button class="modebtn" data-mode="/codeencryption">/codeencryption</button>
      <button class="modebtn" data-mode="/hiddenmode">/hiddenmode</button>
    </div>
  </div>

  <div class="section card modepanel" id="codeModePanel">
    <div class="section-head"><h2 id="codeModeTitle">Code analysis</h2><span class="sub" id="codeModeSubtitle"></span></div>
    <div class="url-summary" id="codeModeSummary"></div>
    <div class="code-toolbar">
      <input id="codeModeSearch" placeholder="Search current code view...">
      <select id="codeFileSelect"><option value="">All files</option></select>
    </div>
    <div class="mode-list" id="codeModeList"></div>
    <div class="code-view" id="codeViewBox" style="display:none"><pre id="codeViewPre"></pre></div>
    <div class="note"><b>Redaction:</b> password/token/key values and private-key material are masked in generated code-analysis output. Locations and variable names remain visible for review.</div>
  </div>

  <div class="section card modepanel" id="deepDivePanel">
    <div class="section-head"><h2>/deep-dive — All detection detail</h2><span class="sub">Evidence • confidence • file/line • rule • surface</span></div>
    <div class="url-summary" id="deepDiveSummary"></div>
    <div class="mode-list" id="deepDiveEvidence"></div>
  </div>

  <div class="section card modepanel" id="securityCheckPanel">
    <div class="section-head"><h2>/securitycheck — Security control review</h2><span class="sub">Priority review areas, not a pass/fail certificate</span></div>
    <div class="url-summary" id="securitySummary"></div>
    <div class="mode-list" id="securityControls"></div>
    <div class="note" id="securityNote"></div>
  </div>

  <div class="section card modepanel" id="anonymousPanel">
    <div class="section-head"><h2>/anonymus — Privacy & identity exposure</h2><span class="sub">Alias: /anonymous</span></div>
    <div class="url-summary" id="anonymousSummary"></div>
    <div class="surface-grid" id="anonymousCards"></div>
    <div class="mode-list" id="anonymousEvidence" style="margin-top:10px"></div>
    <div class="note" id="anonymousNote"></div>
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
    <div class="note">360 view combines file/path inventory, URLs, IP/network, device/privacy/account, encryption/TLS, protocols, hidden surfaces, database/routes and security findings. Use <b>/deep-dive</b> when you want every detection and evidence row.</div>
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
const CODEDATA=DATA.codeData||{};
const NETDATA=DATA.networkData||{};
const PREFLIGHT=DATA.preflightData||{};

function miniMetric(parent,label,value){
  const d=document.createElement('div');d.className='detail';
  const b=document.createElement('b');b.textContent=label;
  const s=document.createElement('span');s.textContent=String(value??'-');
  d.append(b,s);parent.appendChild(d);
}



const PREFLIGHT_MODES=new Set(['/preflight','/viewextraction','/viewurls','/routes','/api','/keys','/hiddentraces','/hidemodes','/hidelog','/ipmirror','/certs']);
let CURRENT_PREFLIGHT_MODE='/preflight';

function preItem(parent,title,meta,body){
  const d=document.createElement('div');d.className='mode-item';
  if(title){const h=document.createElement('strong');h.textContent=title;d.appendChild(h)}
  if(meta){const m=document.createElement('div');m.className='meta';m.textContent=meta;d.appendChild(m)}
  if(body){const b=document.createElement('div');b.textContent=body;d.appendChild(b)}
  parent.appendChild(d);
}
function renderPreflightMode(mode=CURRENT_PREFLIGHT_MODE){
  CURRENT_PREFLIGHT_MODE=mode;
  const titleMap={
    '/preflight':'/preflight — Before-Semgrep target analysis',
    '/viewextraction':'/viewextraction — Imports/functions/classes/config/routes',
    '/viewurls':'/viewurls — Source/final URLs and DNS evidence',
    '/routes':'/routes — Application route declarations',
    '/api':'/api — API/client usage references',
    '/keys':'/keys — Redacted key/password/token references',
    '/hiddentraces':'/hiddentraces — Hidden/stealth-like code detection',
    '/hidemodes':'/hidemodes — Hidden/private/silent mode detection',
    '/hidelog':'/hidelog — Logging suppression/clearing detection',
    '/ipmirror':'/ipmirror — App destination IP mirror',
    '/certs':'/certs — Certificate inventory/public-cert copies'
  };
  $('preflightModeTitle').textContent=titleMap[mode]||'Pre-scan target analysis';
  $('preflightModeSubtitle').textContent=(PREFLIGHT.phase||'before-semgrep')+' · preflight-analysis.json';
  const sum=$('preflightModeSummary');sum.replaceChildren();
  const list=$('preflightModeList');list.replaceChildren();
  const s=PREFLIGHT.summary||{};
  miniMetric(sum,'Files',s.files||0);miniMetric(sum,'URLs',s.urls||0);miniMetric(sum,'Routes',s.routes||0);
  miniMetric(sum,'API refs',s.apiRefs||0);miniMetric(sum,'Key refs',s.keyRefs||0);miniMetric(sum,'Certs',s.certs||0);
  miniMetric(sum,'Hidden traces',s.hiddenTraces||0);miniMetric(sum,'Hide-log refs',s.hideLogRefs||0);

  if(mode==='/viewextraction'){
    const x=PREFLIGHT.viewextraction||{};
    (x.imports||[]).slice(0,1000).forEach(v=>preItem(list,'Import '+(v.module||''),(v.path||'')+':'+(v.line||'?'),''));
    (x.functions||[]).slice(0,1000).forEach(v=>preItem(list,'Function '+(v.name||''),(v.path||'')+':'+(v.line||'?'),''));
    (x.classes||[]).slice(0,1000).forEach(v=>preItem(list,'Class '+(v.name||''),(v.path||'')+':'+(v.line||'?'),''));
    (x.environment||[]).slice(0,1000).forEach(v=>preItem(list,'Environment/config',(v.path||'')+':'+(v.line||'?'),v.preview||''));
    (x.routes||[]).slice(0,1000).forEach(v=>preItem(list,(v.method||'')+' '+(v.route||''),(v.path||'')+':'+(v.line||'?'),''));
  } else if(mode==='/viewurls'){
    (PREFLIGHT.viewurls?.items||[]).forEach(v=>preItem(list,v.sourceUrl||'URL',(v.host||'')+' · '+(v.destinationClass||'')+' · status '+(v.status||'-'),v.finalUrl&&v.finalUrl!==v.sourceUrl?'Final: '+v.finalUrl:''));
  } else if(mode==='/routes'){
    (PREFLIGHT.routes?.items||[]).forEach(v=>preItem(list,(v.method||'')+' '+(v.route||''),(v.path||'')+':'+(v.line||'?'),''));
  } else if(mode==='/api'){
    (PREFLIGHT.api?.items||[]).forEach(v=>preItem(list,v.kind||'api',(v.path||'')+':'+(v.line||'?'),v.preview||''));
  } else if(mode==='/keys'){
    (PREFLIGHT.keys?.items||[]).forEach(v=>preItem(list,v.name||v.kind||'key',(v.path||'')+':'+(v.line||'?'),'Masked: '+(v.masked||'<redacted>')));
  } else if(mode==='/hiddentraces'){
    (PREFLIGHT.hiddentraces?.items||[]).forEach(v=>preItem(list,v.kind||'hidden-trace',(v.path||'')+':'+(v.line||'?'),v.preview||''));
  } else if(mode==='/hidemodes'){
    (PREFLIGHT.hidemodes?.items||[]).forEach(v=>preItem(list,v.kind||'hidden-mode',(v.path||'')+':'+(v.line||'?'),v.preview||''));
  } else if(mode==='/hidelog'){
    (PREFLIGHT.hidelog?.items||[]).forEach(v=>preItem(list,v.kind||'log-suppression',(v.path||'')+':'+(v.line||'?'),v.preview||''));
  } else if(mode==='/ipmirror'){
    (PREFLIGHT.ipmirror?.items||[]).forEach(v=>preItem(list,v.host||'destination',(v.destinationClass||'')+' · '+((v.resolvedIps||[]).join(', ')||'-'),(v.sourceUrl||'')+(v.finalUrl&&v.finalUrl!==v.sourceUrl?' → '+v.finalUrl:'')));
  } else if(mode==='/certs'){
    (PREFLIGHT.certs?.items||[]).forEach(v=>preItem(list,v.kind||'certificate',v.path||'',(v.sha256||'')+' · '+(v.bytes||0)+' bytes'));
    (PREFLIGHT.certs?.copies||[]).forEach(v=>preItem(list,'Copied public certificate',v.source||'',v.copy||v.error||''));
  } else {
    Object.entries(s).forEach(([k,v])=>preItem(list,k,'',String(v)));
    if(PREFLIGHT.capture?.enabled)preItem(list,'Redacted source snapshot','Files '+(PREFLIGHT.capture.files||[]).length,'Stored under .lola-preflight/code');
    if((PREFLIGHT.certs?.copies||[]).length)preItem(list,'Public certificate copies','Count '+PREFLIGHT.certs.copies.length,'Stored under .lola-preflight/certs');
  }
  const notes={
    '/keys':'Secret/key values are masked or not collected.',
    '/hiddentraces':'Detection-only: identifies hidden/stealth-like patterns; it does not enable concealment.',
    '/hidemodes':'Detection-only: identifies hidden/private/silent mode references.',
    '/hidelog':'Detection-only: identifies logging suppression or clearing code. Lola does not erase application, OS, browser, or security logs.',
    '/ipmirror':'Mirrors application destination DNS/IP resolution; it is not a device-geolocation feature.',
    '/certs':'Only public certificate material may be copied. Private key containers are never copied.'
  };
  $('preflightModeNote').textContent=notes[mode]||'This data is generated before the main Semgrep scan.';
  if(!list.children.length)list.innerHTML='<div class="empty">No matching pre-scan evidence.</div>';
}

const NETWORK_MODES=new Set(['/deep-network','/trace','/route','/map','/visible','/realip','/cctv','/normal']);
let CURRENT_NETWORK_MODE='/normal';

function netItem(parent,title,meta,body){
  const d=document.createElement('div');d.className='mode-item';
  if(title){const h=document.createElement('strong');h.textContent=title;d.appendChild(h)}
  if(meta){const m=document.createElement('div');m.className='meta';m.textContent=meta;d.appendChild(m)}
  if(body){const b=document.createElement('div');b.textContent=body;d.appendChild(b)}
  parent.appendChild(d);
}
function renderNetworkMode(mode=CURRENT_NETWORK_MODE){
  CURRENT_NETWORK_MODE=mode;
  const titleMap={
    '/deep-network':'/deep-dive network — Combined network analysis',
    '/trace':'/trace — URL/DNS/redirect/TLS trace',
    '/route':'/route — Application route map',
    '/map':'/map — Logical network graph',
    '/visible':'/visible — Publicly visible source/resolution surface',
    '/realip':'/realip — Resolved public IPs and discovery references',
    '/cctv':'/cctv — Live process monitor',
    '/normal':'/normal — Compact network view'
  };
  $('networkModeTitle').textContent=titleMap[mode]||'Network analysis';
  $('networkModeSubtitle').textContent='network-analysis.json';
  const sum=$('networkModeSummary');sum.replaceChildren();
  const list=$('networkModeList');list.replaceChildren();
  const s=NETDATA.summary||{};
  miniMetric(sum,'URLs',s.urls||0);miniMetric(sum,'Domains',s.domains||0);
  miniMetric(sum,'Public IPs',s.publicIps||0);miniMetric(sum,'Non-public IPs',s.nonPublicIps||0);
  miniMetric(sum,'Redirect hops',s.redirectHops||0);miniMetric(sum,'TLS endpoints',s.tlsEndpoints||0);
  miniMetric(sum,'App routes',s.appRoutes||0);miniMetric(sum,'Network findings',s.networkFindings||0);

  if(mode==='/trace'){
    (NETDATA.trace?.items||[]).forEach(x=>{
      const chain=[x.sourceUrl,...(x.redirects||[]).map(r=>r.to),x.finalUrl&&x.finalUrl!==x.sourceUrl?x.finalUrl:null].filter(Boolean);
      netItem(list,x.host||'URL',(x.destinationClass||'')+' · status '+(x.status||'-')+' · TLS '+(x.tls?.version||'-'),
        chain.join(' → ')+' · IPs '+((x.resolvedIps||[]).join(', ')||'-'));
    });
  } else if(mode==='/route'){
    (NETDATA.route?.items||[]).forEach(x=>netItem(list,(x.method||'')+' '+(x.route||''),(x.path||'')+':'+(x.line||'?'),''));
  } else if(mode==='/map'){
    (NETDATA.map?.nodes||[]).slice(0,350).forEach(x=>netItem(list,'Node · '+(x.kind||''),x.id||'',x.label||''));
    (NETDATA.map?.edges||[]).slice(0,500).forEach(x=>netItem(list,'Edge · '+(x.label||'link'),(x.from||'')+' → '+(x.to||''),''));
  } else if(mode==='/visible'){
    (NETDATA.visible?.publicHosts||[]).forEach(x=>netItem(list,'Host '+x.host,'references '+x.references,''));
    (NETDATA.visible?.publicIps||[]).forEach(x=>netItem(list,'Public IP '+x.ip,'references '+x.references,''));
    (NETDATA.visible?.networkFindings||[]).forEach(x=>netItem(list,(x.severity||'INFO')+' · '+(x.surface||''),(x.path||'')+':'+(x.line||'?'),x.message||x.rule||''));
  } else if(mode==='/realip'){
    (NETDATA.realip?.resolvedPublicIps||[]).forEach(x=>netItem(list,'Resolved public IP '+x.ip,'references '+x.references,''));
    (NETDATA.realip?.publicIpDiscoveryReferences||[]).forEach(x=>netItem(list,'Public-IP discovery service',x.host||'',x.sourceUrl||''));
  } else if(mode==='/cctv'){
    netItem(list,'Live monitor','network-monitor.html','Run the scanner with -LiveMonitor or -Mode /cctv to watch scan-events.json during the process.');
    netItem(list,'Safety','No camera recording','The CCTV-style view shows scan stages and network evidence only.');
  } else if(mode==='/deep-network'){
    (NETDATA.trace?.items||[]).slice(0,80).forEach(x=>netItem(list,'Trace · '+(x.host||'URL'),'status '+(x.status||'-')+' · '+((x.resolvedIps||[]).join(', ')||'-'),x.sourceUrl||''));
    (NETDATA.route?.items||[]).slice(0,80).forEach(x=>netItem(list,'Route · '+(x.method||'')+' '+(x.route||''),(x.path||'')+':'+(x.line||'?'),''));
    (NETDATA.visible?.networkFindings||[]).slice(0,120).forEach(x=>netItem(list,'Finding · '+(x.surface||''),(x.path||'')+':'+(x.line||'?'),x.message||x.rule||''));
  } else {
    (NETDATA.trace?.items||[]).slice(0,20).forEach(x=>netItem(list,x.host||'URL','status '+(x.status||'-')+' · '+((x.resolvedIps||[]).join(', ')||'-'),x.sourceUrl||''));
    (NETDATA.visible?.publicHosts||[]).slice(0,20).forEach(x=>netItem(list,'Host '+x.host,'references '+x.references,''));
  }
  $('networkModeNote').textContent =
    mode==='/realip' ? (NETDATA.realip?.note||'') :
    mode==='/visible' ? (NETDATA.visible?.note||'') :
    mode==='/cctv' ? 'For a live view during scanning, use network-monitor.html through the localhost monitor.' :
    'Network trace is application-layer: source → URL/route → DNS IP → redirect → final URL/TLS. It is not raw ICMP traceroute.';
  if(!list.children.length) list.innerHTML='<div class="empty">No matching network data.</div>';
}

const CODE_MODES=new Set(['/deep-code','/extraction','/codesummary','/codeview','/codepassword','/codestring','/codetransparent','/codemodification','/codefallback','/codeurls','/codeencryption','/hiddenmode']);
let CURRENT_CODE_MODE='/deep-code';

function codeText(x){
  if(x===null||x===undefined)return '';
  if(typeof x==='string'||typeof x==='number'||typeof x==='boolean')return String(x);
  return JSON.stringify(x);
}
function codeItem(parent,title,meta,body){
  const d=document.createElement('div');d.className='mode-item';
  if(title){const h=document.createElement('strong');h.textContent=title;d.appendChild(h)}
  if(meta){const m=document.createElement('div');m.className='meta';m.textContent=meta;d.appendChild(m)}
  if(body){const b=document.createElement('div');b.textContent=body;d.appendChild(b)}
  parent.appendChild(d);
}
function fillCodeFiles(){
  const sel=$('codeFileSelect');
  const old=sel.value;
  while(sel.options.length>1)sel.remove(1);
  const files=[...new Set((CODEDATA.codeview?.files||[]).map(x=>x.path).filter(Boolean))].sort();
  files.forEach(f=>{const o=document.createElement('option');o.value=f;o.textContent=f;sel.appendChild(o)});
  if(files.includes(old))sel.value=old;
}
function renderCodeMode(mode=CURRENT_CODE_MODE){
  CURRENT_CODE_MODE=mode;
  const q=$('codeModeSearch').value.trim().toLowerCase();
  const fileFilter=$('codeFileSelect').value;
  const titleMap={
    '/deep-code':'/deep-dive code — Combined source analysis',
    '/extraction':'/extraction — Symbols, imports, environment and routes',
    '/codesummary':'/codesummary — Repository/source summary',
    '/codeview':'/codeview — Redacted source browser',
    '/codepassword':'/codepassword — Password/token/key references',
    '/codestring':'/codestring — String literal inventory',
    '/codetransparent':'/codetransparent — Data source/sink transparency',
    '/codemodification':'/codemodification — State/file/data modification points',
    '/codefallback':'/codefallback — Error, retry and fallback paths',
    '/codeurls':'/codeurls — URLs and final destinations',
    '/codeencryption':'/codeencryption — Crypto/password/key usage',
    '/hiddenmode':'/hiddenmode — Hidden code/UI/config evidence'
  };
  $('codeModeTitle').textContent=titleMap[mode]||'Code analysis';
  $('codeModeSubtitle').textContent='code-analysis.json';
  const sum=$('codeModeSummary');sum.replaceChildren();
  const list=$('codeModeList');list.replaceChildren();
  $('codeViewBox').style.display='none';
  const s=CODEDATA.summary||{};
  miniMetric(sum,'Files',s.filesIndexed||0);miniMetric(sum,'Lines',s.totalLines||0);
  miniMetric(sum,'Functions',s.functions||0);miniMetric(sum,'Classes',s.classes||0);
  miniMetric(sum,'Secret refs',s.secretRefs||0);miniMetric(sum,'URLs',s.urlRefs||0);

  const match=(obj)=>{
    const txt=JSON.stringify(obj).toLowerCase();
    const f=obj?.path||obj?.occurrences?.[0]?.path||'';
    return (!q||txt.includes(q))&&(!fileFilter||f===fileFilter||txt.includes(fileFilter.toLowerCase()));
  };

  if(mode==='/codesummary'){
    const cs=CODEDATA.codesummary||{};
    Object.entries(cs.summary||{}).forEach(([k,v])=>codeItem(list,k,'',codeText(v)));
    (cs.largestFiles||[]).filter(match).forEach(x=>codeItem(list,x.path,(x.lines??'?')+' lines',String(x.bytes||0)+' bytes'));
  } else if(mode==='/extraction'){
    const ex=CODEDATA.extraction||{};
    (ex.imports||[]).filter(match).forEach(x=>codeItem(list,'Import '+x.module,x.path+':'+x.line,''));
    (ex.functions||[]).filter(match).forEach(x=>codeItem(list,'Function '+x.name,x.path+':'+x.line,''));
    (ex.classes||[]).filter(match).forEach(x=>codeItem(list,'Class '+x.name,x.path+':'+x.line,''));
    (ex.environment||[]).filter(match).forEach(x=>codeItem(list,'Environment/config',x.path+':'+x.line,x.preview||''));
    (ex.routes||[]).filter(match).forEach(x=>codeItem(list,x.method+' '+x.route,x.path+':'+x.line,''));
  } else if(mode==='/codeview'){
    const files=(CODEDATA.codeview?.files||[]).filter(x=>(!fileFilter||x.path===fileFilter)&&(!q||(x.path||'').toLowerCase().includes(q)||(x.view||'').toLowerCase().includes(q)));
    if(files.length===1){
      $('codeViewBox').style.display='block';$('codeViewPre').textContent=files[0].view||'[No embedded source preview]';
      codeItem(list,files[0].path,(files[0].lines??'?')+' lines'+(files[0].truncated?' · preview truncated':''),'');
    } else {
      files.forEach(x=>codeItem(list,x.path,(x.lines??'?')+' lines'+(x.truncated?' · preview truncated':''),'Select this file in the file filter to view its redacted source preview.'));
    }
  } else if(mode==='/codepassword'){
    (CODEDATA.codepassword?.items||[]).filter(match).forEach(x=>codeItem(list,x.type+' · '+x.name,x.path+':'+x.line,'Masked: '+(x.masked||'<redacted>')));
  } else if(mode==='/codestring'){
    (CODEDATA.codestring?.items||[]).filter(match).forEach(x=>codeItem(list,x.sensitive?'Sensitive string (redacted)':'String',x.path+':'+x.line,x.value||''));
  } else if(mode==='/codetransparent'){
    (CODEDATA.codetransparent?.files||[]).filter(match).forEach(x=>codeItem(list,x.path,'Sources: '+(x.sourceTypes||[]).join(', ')+' · Sinks: '+(x.sinkTypes||[]).join(', '),'Source count '+(x.sources||[]).length+' · Sink count '+(x.sinks||[]).length));
  } else if(mode==='/codemodification'){
    (CODEDATA.codemodification?.items||[]).filter(match).forEach(x=>codeItem(list,x.kind,x.path+':'+x.line,x.preview||''));
  } else if(mode==='/codefallback'){
    (CODEDATA.codefallback?.items||[]).filter(match).forEach(x=>codeItem(list,x.kind,x.path+':'+x.line,x.preview||''));
  } else if(mode==='/codeurls'){
    (CODEDATA.codeurls?.items||[]).filter(match).forEach(x=>codeItem(list,x.sourceUrl||'URL',(x.scheme||'')+' · '+(x.host||'')+' · '+(x.destinationClass||''),(x.finalUrl&&x.finalUrl!==x.sourceUrl?'Final: '+x.finalUrl:'')+' '+((x.resolvedIps||[]).join(', '))));
  } else if(mode==='/codeencryption'){
    (CODEDATA.codeencryption?.items||[]).filter(match).forEach(x=>codeItem(list,x.kind+(x.passwordOrKeyRelated?' · password/key related':''),x.path+':'+x.line,x.preview||''));
  } else if(mode==='/hiddenmode'){
    (CODEDATA.hiddenmode?.items||[]).filter(match).forEach(x=>codeItem(list,x.kind,x.path+':'+x.line,x.preview||''));
    (MODEDATA.hidden?.files||[]).filter(match).forEach(x=>codeItem(list,'Hidden/sensitive file',x.reason||'',x.path||x.name||''));
  } else {
    const sections=[
      ['Extraction',CODEDATA.extraction?.functions?.length||0],
      ['Imports',CODEDATA.extraction?.imports?.length||0],
      ['Password/key refs',CODEDATA.codepassword?.items?.length||0],
      ['Strings',CODEDATA.codestring?.items?.length||0],
      ['Transparent-flow files',CODEDATA.codetransparent?.files?.length||0],
      ['Modification points',CODEDATA.codemodification?.items?.length||0],
      ['Fallback points',CODEDATA.codefallback?.items?.length||0],
      ['URLs',CODEDATA.codeurls?.items?.length||0],
      ['Crypto refs',CODEDATA.codeencryption?.items?.length||0],
      ['Hidden code refs',CODEDATA.hiddenmode?.items?.length||0]
    ];
    sections.forEach(([a,b])=>codeItem(list,a,'',String(b)));
    (CODEDATA.codepassword?.items||[]).filter(match).slice(0,40).forEach(x=>codeItem(list,'Secret ref · '+x.name,x.path+':'+x.line,'Masked: '+(x.masked||'<redacted>')));
    (CODEDATA.codeencryption?.items||[]).filter(match).slice(0,40).forEach(x=>codeItem(list,'Crypto · '+x.kind,x.path+':'+x.line,x.preview||''));
    (CODEDATA.codemodification?.items||[]).filter(match).slice(0,40).forEach(x=>codeItem(list,'Modification · '+x.kind,x.path+':'+x.line,x.preview||''));
  }
  if(!list.children.length && $('codeViewBox').style.display==='none')list.innerHTML='<div class="empty">No matching code-analysis entries.</div>';
}

function renderModes(){
  const dd=MODEDATA['deep-dive']||{};
  const ds=$('deepDiveSummary');ds.replaceChildren();
  const dsm=dd.summary||{};
  miniMetric(ds,'Detections',dsm.total||0);miniMetric(ds,'Errors',dsm.errors||0);miniMetric(ds,'Warnings',dsm.warnings||0);miniMetric(ds,'Rules',dsm.rules||0);
  miniMetric(ds,'Files',dsm.affectedFiles||0);miniMetric(ds,'Surfaces',dsm.surfaces||0);
  const de=$('deepDiveEvidence');de.replaceChildren();
  (dd.detections||[]).forEach(x=>{
    const d=document.createElement('div');d.className='mode-item';
    const head=document.createElement('strong');head.textContent=(x.severity||'INFO')+' · '+(x.surface||x.category||'other')+' · '+(x.rule||'');
    const loc=document.createElement('div');loc.className='meta';loc.textContent=(x.path||'[unknown]')+(x.line?':'+x.line+(x.col?':'+x.col:''):'')+(x.confidence?' · confidence '+x.confidence:'')+(x.cwe?' · '+x.cwe:'');
    const msg=document.createElement('div');msg.textContent=x.message||'';
    d.append(head,loc,msg);
    if(x.lines){const pre=document.createElement('pre');pre.textContent=x.lines;d.appendChild(pre)}
    de.appendChild(d);
  });
  if(!de.children.length) de.innerHTML='<div class="empty">No detections.</div>';

  const sc=MODEDATA.securitycheck||{};
  const ss=$('securitySummary');ss.replaceChildren();
  const sm=sc.summary||{};
  miniMetric(ss,'Control groups',sm.controls||0);miniMetric(ss,'Priority review',sm.priorityReview||0);miniMetric(ss,'Review',sm.review||0);miniMetric(ss,'No detection',sm.noDetection||0);
  miniMetric(ss,'Errors',sm.errors||0);miniMetric(ss,'Warnings',sm.warnings||0);
  const ctr=$('securityControls');ctr.replaceChildren();
  (sc.controls||[]).forEach(x=>{
    const d=document.createElement('div');d.className='mode-item';
    const title=document.createElement('strong');title.textContent=(x.state==='priority-review'?'🔴 ':x.state==='review'?'🟠 ':'⚪ ')+x.name+' — '+x.total+' findings';
    const counts=document.createElement('div');counts.className='meta';counts.textContent='Errors '+x.errors+' · Warnings '+x.warnings+' · Info '+x.info;
    const rev=document.createElement('div');rev.textContent=x.review||'';
    d.append(title,counts,rev);ctr.appendChild(d);
  });
  $('securityNote').textContent=sc.note||'';

  const an=MODEDATA.anonymous||{};
  const as=$('anonymousSummary');as.replaceChildren();
  const am=an.summary||{};
  miniMetric(as,'Exposure findings',am.exposureFindings||0);miniMetric(as,'IP/tracking URLs',am.publicIpOrTrackingUrls||0);miniMetric(as,'Fingerprinting',am.fingerprinting||0);miniMetric(as,'Telemetry',am.telemetry||0);
  miniMetric(as,'Persistent IDs',am.persistentIds||0);miniMetric(as,'Network exposure',am.networkExposure||0);miniMetric(as,'Account linkage',am.accountLinkage||0);
  const ac=$('anonymousCards');ac.replaceChildren();
  Object.entries(an.counts||{}).sort((a,b)=>b[1]-a[1]).forEach(([name,count])=>{
    const d=document.createElement('div');d.className='surface';const t=document.createElement('div');t.className='surface-top';
    const n=document.createElement('div');n.className='surface-name';n.textContent='🕶️ '+name;const v=document.createElement('div');v.className='surface-count';v.textContent=count;t.append(n,v);d.appendChild(t);ac.appendChild(d);
  });
  if(!ac.children.length) ac.innerHTML='<div class="empty">No privacy/identity exposure detections.</div>';
  const ae=$('anonymousEvidence');ae.replaceChildren();
  (an.findings||[]).slice(0,150).forEach(x=>{const d=document.createElement('div');d.className='mode-item';d.textContent=(x.surface||x.category||'privacy')+' · '+(x.path||'')+(x.line?':'+x.line:'')+' — '+(x.message||x.rule||'');ae.appendChild(d)});
  (an.urls||[]).slice(0,100).forEach(x=>{const d=document.createElement('div');d.className='mode-item';d.textContent='URL · '+(x.sourceUrl||'')+(x.finalUrl&&x.finalUrl!==x.sourceUrl?' → '+x.finalUrl:'');ae.appendChild(d)});
  $('anonymousNote').textContent=an.note||'';

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
  (MODEDATA.protocol?.findings||[]).slice(0,100).forEach(x=>{const d=document.createElement('div');d.className='mode-item';d.textContent=(x.surface||x.category||'protocol')+' • '+(x.path||'')+(x.line?':'+x.line:'')+' — '+(x.message||x.rule||'');pe.appendChild(d)});

  const hs=$('hiddenSummary');hs.replaceChildren();
  const hc=MODEDATA.hidden?.counts||{};
  miniMetric(hs,'Hidden/sensitive files',hc.files||0);miniMetric(hs,'Hidden findings',hc.findings||0);miniMetric(hs,'Dot paths',hc.dotPaths||0);miniMetric(hs,'Sensitive config',hc.sensitiveConfig||0);
  const he=$('hiddenEvidence');he.replaceChildren();
  (MODEDATA.hidden?.files||[]).slice(0,100).forEach(x=>{const d=document.createElement('div');d.className='mode-item';d.textContent=(x.reason||'hidden')+' • '+(x.path||x.name||'');he.appendChild(d)});
  (MODEDATA.hidden?.findings||[]).slice(0,100).forEach(x=>{const d=document.createElement('div');d.className='mode-item';d.textContent=(x.surface||'hidden')+' • '+(x.path||'')+(x.line?':'+x.line:'')+' — '+(x.message||x.rule||'');he.appendChild(d)});

  const vs=$('view360Summary');vs.replaceChildren();
  const vsm=MODEDATA['360']?.summary||{};
  miniMetric(vs,'Files',vsm.files||0);miniMetric(vs,'URLs',vsm.urls||0);miniMetric(vs,'Findings',vsm.findings||0);miniMetric(vs,'Errors',vsm.errors||0);
  miniMetric(vs,'Warnings',vsm.warnings||0);miniMetric(vs,'Protocols',vsm.protocolSurfaces||0);miniMetric(vs,'Hidden files',vsm.hiddenFiles||0);miniMetric(vs,'Privacy exposures',vsm.privacyExposures||0);
  miniMetric(vs,'Control groups review',vsm.controlGroupsReview||0);miniMetric(vs,'Info',vsm.info||0);
}
function setMode(mode){
  let normalized=mode.startsWith('/')?mode:'/'+mode;
  if(normalized==='/protocal') normalized='/protocol';
  if(normalized==='/deepdive') normalized='/deep-dive';
  if(normalized==='/anonymous') normalized='/anonymus';
  if(normalized==='/deep-dive code'||normalized==='/deep-dive-code') normalized='/deep-code';
  if(normalized==='/deep-dive network'||normalized==='/deep-dive-network') normalized='/deep-network';
  document.querySelectorAll('.modebtn').forEach(b=>b.classList.toggle('active',b.dataset.mode===normalized));
  const map={
    '/deep-dive':'deepDivePanel','/securitycheck':'securityCheckPanel','/anonymus':'anonymousPanel',
    '/stepview':'stepviewPanel','/protocol':'protocolPanel','/hidden':'hiddenPanel','/360':'view360Panel',
    '/deep-code':'codeModePanel','/extraction':'codeModePanel','/codesummary':'codeModePanel','/codeview':'codeModePanel',
    '/codepassword':'codeModePanel','/codestring':'codeModePanel','/codetransparent':'codeModePanel',
    '/codemodification':'codeModePanel','/codefallback':'codeModePanel','/codeurls':'codeModePanel',
    '/codeencryption':'codeModePanel','/hiddenmode':'codeModePanel',
    '/deep-network':'networkModePanel','/trace':'networkModePanel','/route':'networkModePanel',
    '/map':'networkModePanel','/visible':'networkModePanel','/realip':'networkModePanel',
    '/cctv':'networkModePanel','/normal':'networkModePanel',
    '/preflight':'preflightModePanel','/viewextraction':'preflightModePanel','/viewurls':'preflightModePanel',
    '/routes':'preflightModePanel','/api':'preflightModePanel','/keys':'preflightModePanel',
    '/hiddentraces':'preflightModePanel','/hidemodes':'preflightModePanel','/hidelog':'preflightModePanel',
    '/ipmirror':'preflightModePanel','/certs':'preflightModePanel'
  };
  document.querySelectorAll('.modepanel').forEach(p=>p.classList.remove('active'));
  const panel=$(map[normalized]||'view360Panel');if(panel)panel.classList.add('active');
  if(CODE_MODES.has(normalized)){renderCodeMode(normalized)}
  if(NETWORK_MODES.has(normalized)){renderNetworkMode(normalized)}
  if(PREFLIGHT_MODES.has(normalized)){renderPreflightMode(normalized)}
  if(normalized==='/protocol'){$('category').value='protocol';render()}
  else if(normalized==='/hidden'){$('category').value='hidden';render()}
  else if(normalized==='/anonymus'){$('category').value='privacy';render()}
  else if(normalized==='/securitycheck'){$('category').value='';render()}
  else if(normalized==='/deep-dive'){$('category').value='';$('surface').value='';$('search').value='';render()}
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
  'device-files':'🗃️','account-auth':'👤','personal-data':'👥','device-biometric':'🔐','device-notifications':'🔔',
  'privacy-ip-exposure':'🌐','privacy-telemetry':'📡','privacy-persistent-id':'🪪','privacy-fingerprinting':'🕵️',
  'privacy-network-exposure':'🛜','privacy-advertising-id':'🎯','privacy-cookie':'🍪'
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
fillCodeFiles();
$('codeModeSearch').addEventListener('input',()=>renderCodeMode(CURRENT_CODE_MODE));
$('codeFileSelect').addEventListener('change',()=>renderCodeMode(CURRENT_CODE_MODE));
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

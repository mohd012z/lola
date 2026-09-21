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
.section{margin-top:16px}.section-head{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:10px}.section h2{font-size:17px;margin:0}
.surface-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}.surface{cursor:pointer;background:var(--panel3);border:1px solid var(--line);border-radius:13px;padding:13px;transition:.15s}.surface:hover{transform:translateY(-1px);border-color:#536d9f}.surface.active{outline:2px solid var(--accent)}.surface-top{display:flex;justify-content:space-between;gap:8px}.surface-name{font-weight:750}.surface-count{font-size:22px;font-weight:850}.mini{display:flex;gap:7px;margin-top:7px;font-size:11px;color:var(--muted)}.dotE{color:var(--error)}.dotW{color:var(--warn)}.dotI{color:var(--info)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}.bars{display:grid;gap:9px}.bar-row{display:grid;grid-template-columns:minmax(120px,220px) 1fr 46px;gap:10px;align-items:center}.bar-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.bar-bg{height:10px;background:#091223;border:1px solid #22304e;border-radius:99px;overflow:hidden}.bar-fill{height:100%;background:linear-gradient(90deg,#628eff,#9674ff);border-radius:inherit}
.controls{display:grid;grid-template-columns:minmax(240px,1.5fr) repeat(5,minmax(130px,1fr));gap:9px;margin-top:16px}.controls input,.controls select{width:100%;background:#0b1426;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px 11px}
.findings{display:grid;gap:10px}.finding{background:var(--panel);border:1px solid var(--line);border-left-width:4px;border-radius:13px;padding:14px}.finding.ERROR{border-left-color:var(--error)}.finding.WARNING{border-left-color:var(--warn)}.finding.INFO{border-left-color:var(--info)}
.row{display:flex;gap:12px;align-items:flex-start;justify-content:space-between}.left{min-width:0}.msg{font-weight:750;margin-bottom:5px}.meta{color:var(--muted);font-size:12px;word-break:break-all}.pill{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:99px;padding:3px 8px;font-size:11px;margin:0 0 5px 5px}.sev.ERROR{color:var(--error)}.sev.WARNING{color:var(--warn)}.sev.INFO{color:var(--info)}
details{margin-top:10px}summary{cursor:pointer;color:#bfd1ff}.detail-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin-top:10px}.detail{background:#0b1426;border:1px solid #22304e;border-radius:9px;padding:9px;min-width:0;overflow-wrap:anywhere}.detail b{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;margin-bottom:3px}pre{white-space:pre-wrap;overflow:auto;background:#070d19;border:1px solid #22304e;border-radius:9px;padding:11px;color:#dce7ff}
.note{margin-top:12px;padding:11px 13px;border-radius:11px;background:#0c172b;border:1px solid #233a63;color:#b9c9e7}.manifest-tools{display:flex;gap:10px;align-items:center;margin-bottom:10px}.manifest-tools input{flex:1;background:#0b1426;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px 11px}.manifest{max-height:460px;overflow:auto;border:1px solid var(--line);border-radius:12px}.mf{display:grid;grid-template-columns:minmax(280px,1fr) 90px 90px 110px minmax(180px,.7fr);gap:10px;padding:10px 12px;border-bottom:1px solid #1d2d4b;align-items:center}.mf:last-child{border-bottom:0}.mfpath{word-break:break-all}.mf small{color:var(--muted)}.hash{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;word-break:break-all;color:#b8caef}.empty{padding:34px;text-align:center;color:var(--muted)}.footer{color:var(--muted);font-size:12px;margin:18px 0}
@media(max-width:1100px){.controls{grid-template-columns:1fr 1fr 1fr}.detail-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}.hero{display:block}}
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

  <div class="section card">
    <div class="section-head"><h2>Attack-surface map</h2><span class="sub">Click a surface to filter findings</span></div>
    <div class="surface-grid" id="surfaces"></div>
    <div class="note">Client-IP findings show where the application reads peer/proxy IP information such as <b>req.ip</b>, <b>X-Forwarded-For</b>, <b>X-Real-IP</b>, or similar headers. They do not independently discover a person's physical location. Forwarded headers are trustworthy only when the proxy chain is correctly controlled/configured.</div>
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
const ICONS={
  filesystem:'🗂️','http-files':'📦',uploads:'⬆️','http-routes':'🛣️','browser-navigation':'🧭',
  'network-addresses':'🌐','private-network':'🏠','client-ip':'🛰️','proxy-trust':'🛡️',
  listeners:'📡',dns:'🔎',encryption:'🔐',webcrypto:'🔒','key-derivation':'🗝️',random:'🎲',
  signatures:'✍️',tls:'🔏',database:'🗄️',inventory:'📋',security:'⚠️',secrets:'🔑',storage:'💾'
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

function renderBars(rootId,items){
  const root=$(rootId),max=Math.max(1,...items.map(x=>x[1]));
  if(!items.length){root.innerHTML='<div class="empty">No data</div>';return}
  items.forEach(([name,count])=>{const row=document.createElement('div');row.className='bar-row';const n=document.createElement('div');n.className='bar-name';n.textContent=name;n.title=name;const bg=document.createElement('div');bg.className='bar-bg';const fill=document.createElement('div');fill.className='bar-fill';fill.style.width=(count/max*100)+'%';bg.appendChild(fill);const c=document.createElement('div');c.textContent=count;row.append(n,bg,c);root.appendChild(row)})
}
renderBars('ruleBars',DATA.topRules||[]);renderBars('fileBars',DATA.topFiles||[]);

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
render();
</script>
</body>
</html>""".replace("__DATA__", data)

    Path(args.output).write_text(page, encoding="utf-8")
    print(f"Visual report written: {Path(args.output).resolve()}")

if __name__ == "__main__":
    main()

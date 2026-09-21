#!/usr/bin/env python3
import argparse
import html
import json
from collections import Counter
from pathlib import Path

def esc(value):
    return html.escape("" if value is None else str(value), quote=True)

def normalize(result):
    extra = result.get("extra") or {}
    start = result.get("start") or {}
    end = result.get("end") or {}
    metadata = extra.get("metadata") or {}
    return {
        "rule": result.get("check_id") or "unknown-rule",
        "severity": str(extra.get("severity") or "INFO").upper(),
        "message": extra.get("message") or "",
        "path": result.get("path") or "",
        "line": start.get("line") or 0,
        "col": start.get("col") or 0,
        "endLine": end.get("line") or 0,
        "category": metadata.get("category") or "other",
        "cwe": metadata.get("cwe") or "",
        "confidence": metadata.get("confidence") or "",
        "lines": ((extra.get("lines") or "").strip()),
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="semgrep-results.json")
    p.add_argument("--output", default="semgrep-report.html")
    p.add_argument("--target", default="")
    args = p.parse_args()

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"Input not found: {src}")

    raw = json.loads(src.read_text(encoding="utf-8"))
    findings = [normalize(r) for r in raw.get("results", [])]

    sev = Counter(x["severity"] for x in findings)
    cats = Counter(x["category"] for x in findings)
    rules = Counter(x["rule"] for x in findings)
    files = Counter(x["path"] for x in findings if x["path"])

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
        "topRules": rules.most_common(8),
        "findings": findings,
    }

    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")

    page = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codex Security Report</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#121a2d;--panel2:#17213a;--text:#edf2ff;--muted:#9daccc;--line:#263556;--error:#ff647c;--warn:#ffbf5a;--info:#62a8ff;--ok:#55d6a6}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#08101f,#0d1425 36%,#0b1020);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1380px;margin:auto;padding:24px}.hero{display:flex;gap:18px;justify-content:space-between;align-items:flex-start;margin-bottom:18px}.hero h1{margin:0 0 5px;font-size:28px}.sub{color:var(--muted);word-break:break-all}
.grid{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:12px}.card{background:rgba(18,26,45,.96);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:0 12px 35px #0003}.metric{font-size:30px;font-weight:800}.label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.error .metric{color:var(--error)}.warning .metric{color:var(--warn)}.info .metric{color:var(--info)}
.section{margin-top:16px}.section-head{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:10px}.section h2{font-size:17px;margin:0}
.controls{display:grid;grid-template-columns:minmax(220px,1fr) repeat(3,minmax(150px,220px));gap:10px;margin-top:16px}
input,select,button{width:100%;background:#0d1527;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
button{cursor:pointer}button.active{outline:2px solid #718cff}
.bars{display:grid;gap:9px}.bar-row{display:grid;grid-template-columns:190px 1fr 50px;gap:10px;align-items:center}.bar-bg{height:10px;background:#0c1426;border:1px solid #22304e;border-radius:99px;overflow:hidden}.bar-fill{height:100%;background:linear-gradient(90deg,#658bff,#8f72ff);border-radius:inherit}
.findings{display:grid;gap:10px}.finding{background:var(--panel);border:1px solid var(--line);border-left-width:4px;border-radius:13px;padding:14px}.finding.ERROR{border-left-color:var(--error)}.finding.WARNING{border-left-color:var(--warn)}.finding.INFO{border-left-color:var(--info)}
.row{display:flex;gap:10px;align-items:flex-start;justify-content:space-between}.left{min-width:0}.msg{font-weight:700;margin-bottom:5px}.meta{color:var(--muted);font-size:12px;word-break:break-all}.pill{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:99px;padding:3px 8px;font-size:11px;margin-right:5px}.sev.ERROR{color:var(--error)}.sev.WARNING{color:var(--warn)}.sev.INFO{color:var(--info)}
details{margin-top:10px}summary{cursor:pointer;color:#bdd0ff}.detail-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px}.detail{background:#0d1527;border:1px solid #22304e;border-radius:9px;padding:9px}.detail b{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;margin-bottom:3px}
pre{white-space:pre-wrap;overflow:auto;background:#080e1b;border:1px solid #22304e;border-radius:9px;padding:11px;color:#dce7ff}
.empty{padding:40px;text-align:center;color:var(--muted)}.footer{color:var(--muted);font-size:12px;margin:18px 0}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.controls{grid-template-columns:1fr 1fr}.detail-grid{grid-template-columns:1fr 1fr}.bar-row{grid-template-columns:120px 1fr 42px}.hero{display:block}}
@media(max-width:560px){.wrap{padding:14px}.grid,.controls,.detail-grid{grid-template-columns:1fr}.row{display:block}.bar-row{grid-template-columns:100px 1fr 38px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div><h1>🛡️ Codex Security Report</h1><div class="sub" id="target"></div></div>
    <div class="sub">Generated from Semgrep JSON</div>
  </div>

  <div class="grid">
    <div class="card"><div class="label">Total findings</div><div class="metric" id="total">0</div></div>
    <div class="card error"><div class="label">Errors</div><div class="metric" id="errors">0</div></div>
    <div class="card warning"><div class="label">Warnings</div><div class="metric" id="warnings">0</div></div>
    <div class="card info"><div class="label">Info / inventory</div><div class="metric" id="infos">0</div></div>
    <div class="card"><div class="label">Affected files</div><div class="metric" id="files">0</div></div>
  </div>

  <div class="section card">
    <div class="section-head"><h2>Top triggered rules</h2><span class="sub">Relative frequency</span></div>
    <div class="bars" id="ruleBars"></div>
  </div>

  <div class="controls">
    <input id="search" placeholder="Search file, rule, message, CWE...">
    <select id="severity"><option value="">All severities</option><option>ERROR</option><option>WARNING</option><option>INFO</option></select>
    <select id="category"><option value="">All categories</option></select>
    <select id="rule"><option value="">All rules</option></select>
  </div>

  <div class="section">
    <div class="section-head"><h2>Findings</h2><span class="sub" id="shown"></span></div>
    <div class="findings" id="findings"></div>
  </div>

  <div class="footer">Review findings in context. A finding is a signal, not proof of exploitability; a clean scan is not proof of complete security.</div>
</div>
<script id="semgrep-data" type="application/json">__DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('semgrep-data').textContent);
const $=id=>document.getElementById(id);
$('target').textContent=DATA.target ? 'Target: '+DATA.target : 'Target not recorded';
$('total').textContent=DATA.total;
$('errors').textContent=DATA.counts.ERROR||0;
$('warnings').textContent=DATA.counts.WARNING||0;
$('infos').textContent=DATA.counts.INFO||0;
$('files').textContent=DATA.affectedFiles||0;

function fillSelect(el, values){values.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;el.appendChild(o)})}
fillSelect($('category'), Object.keys(DATA.categories||{}).sort());
fillSelect($('rule'), [...new Set(DATA.findings.map(x=>x.rule))].sort());

const maxRule=Math.max(1,...DATA.topRules.map(x=>x[1]));
DATA.topRules.forEach(([name,count])=>{
  const row=document.createElement('div'); row.className='bar-row';
  const n=document.createElement('div'); n.textContent=name; n.title=name;
  const bg=document.createElement('div'); bg.className='bar-bg';
  const fill=document.createElement('div'); fill.className='bar-fill'; fill.style.width=(count/maxRule*100)+'%'; bg.appendChild(fill);
  const c=document.createElement('div'); c.textContent=count;
  row.append(n,bg,c); $('ruleBars').appendChild(row);
});
if(!DATA.topRules.length){const e=document.createElement('div');e.className='empty';e.textContent='No findings';$('ruleBars').appendChild(e)}

function addText(parent, tag, text, cls){const el=document.createElement(tag); if(cls)el.className=cls; el.textContent=text; parent.appendChild(el); return el}
function detailBox(parent,label,value){const d=document.createElement('div');d.className='detail';addText(d,'b',label);addText(d,'span',value||'-');parent.appendChild(d)}

function render(){
  const q=$('search').value.trim().toLowerCase();
  const sev=$('severity').value, cat=$('category').value, rule=$('rule').value;
  const rows=DATA.findings.filter(x=>{
    const hay=[x.path,x.rule,x.message,x.cwe,x.category,x.lines].join(' ').toLowerCase();
    return (!q||hay.includes(q))&&(!sev||x.severity===sev)&&(!cat||x.category===cat)&&(!rule||x.rule===rule);
  });
  $('shown').textContent=rows.length+' of '+DATA.findings.length;
  const root=$('findings'); root.replaceChildren();
  if(!rows.length){addText(root,'div','No findings match the current filters.','empty');return}
  rows.forEach(x=>{
    const card=document.createElement('div');card.className='finding '+x.severity;
    const row=document.createElement('div');row.className='row';
    const left=document.createElement('div');left.className='left';
    addText(left,'div',x.message||x.rule,'msg');
    addText(left,'div',(x.path||'[unknown file]')+(x.line?':'+x.line:'')+'  •  '+x.rule,'meta');
    const tags=document.createElement('div');
    const s=addText(tags,'span',x.severity,'pill sev '+x.severity);
    if(x.category)addText(tags,'span',x.category,'pill');
    if(x.cwe)addText(tags,'span',x.cwe,'pill');
    row.append(left,tags);card.appendChild(row);

    const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='View technical detail';details.appendChild(summary);
    const grid=document.createElement('div');grid.className='detail-grid';
    detailBox(grid,'Rule',x.rule);detailBox(grid,'Category',x.category);detailBox(grid,'Confidence',x.confidence);detailBox(grid,'Location',x.line?('Line '+x.line+', col '+x.col):'-');
    details.appendChild(grid);
    if(x.lines){const pre=document.createElement('pre');pre.textContent=x.lines;details.appendChild(pre)}
    card.appendChild(details);root.appendChild(card);
  });
}
['search','severity','category','rule'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',render));
render();
</script>
</body>
</html>""".replace("__DATA__", data)

    Path(args.output).write_text(page, encoding="utf-8")
    print(f"Visual report written: {Path(args.output).resolve()}")

if __name__ == "__main__":
    main()

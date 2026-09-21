#!/usr/bin/env python3
import argparse, html, json
from pathlib import Path

def esc(v): return html.escape(str(v if v is not None else ""))
def badge(text, cls=""): return f'<span class="pill {cls}">{esc(text)}</span>'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default="apk-analysis.json")
    ap.add_argument("--output",default="apk-report.html")
    ap.add_argument("--mode",default="/apk360")
    args=ap.parse_args()
    data=json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    blob=json.dumps(data,ensure_ascii=False).replace("</","<\\/")
    page=r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lola APK Deep Scan</title>
<style>
:root{color-scheme:dark;--bg:#07101d;--panel:#101a2d;--panel2:#0b1426;--line:#283a5a;--text:#eef4ff;--muted:#9cafca;--accent:#74a8ff;--ok:#59d8a8;--warn:#ffc45e;--bad:#ff6d82}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#152744,#07101d 55%);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1500px;margin:auto;padding:18px}.hero{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.hero h1{margin:0;font-size:28px}.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px;margin:14px 0}.card{background:rgba(16,26,45,.97);border:1px solid var(--line);border-radius:15px;padding:14px}.metric{font-size:25px;font-weight:800}.label{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.modebar{display:flex;gap:7px;flex-wrap:wrap;margin:11px 0}.modebtn{background:#13213a;color:var(--text);border:1px solid var(--line);border-radius:999px;padding:8px 11px;cursor:pointer}.modebtn.active{outline:2px solid var(--accent);background:#1a2b4a}
.panel{display:none}.panel.active{display:block}.list{display:grid;gap:8px}.item{background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:10px;word-break:break-word}.meta{font-size:12px;color:var(--muted);margin-top:3px}.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 7px;font-size:11px;margin:2px}.bad{color:var(--bad)}.warn{color:var(--warn)}.ok{color:var(--ok)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:11px}.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.toolbar input,.toolbar select{background:#0a1425;color:var(--text);border:1px solid var(--line);border-radius:9px;padding:9px 10px;min-width:220px}
pre{white-space:pre-wrap;word-break:break-word;background:#060c17;border:1px solid var(--line);border-radius:11px;padding:11px;max-height:620px;overflow:auto}.note{background:#0d1b31;border:1px solid #29466d;border-radius:11px;padding:10px;margin-top:10px;color:#c1d1ea}
table{width:100%;border-collapse:collapse}td,th{padding:7px;border-bottom:1px solid #20314e;text-align:left;vertical-align:top}
@media(max-width:850px){.wrap{padding:12px}.hero{display:block}.two{grid-template-columns:1fr}.toolbar input,.toolbar select{width:100%;min-width:0}}
</style></head><body>
<div class="wrap">
  <div class="hero">
    <div><h1>📦 Lola APK Deep Scan</h1><div class="muted" id="apkPath"></div></div>
    <div id="sha" class="muted"></div>
  </div>

  <div class="grid">
    <div class="card"><div class="label">Package</div><div class="metric" id="pkg">-</div></div>
    <div class="card"><div class="label">Entries</div><div class="metric" id="entries">0</div></div>
    <div class="card"><div class="label">Permissions</div><div class="metric" id="permissions">0</div></div>
    <div class="card"><div class="label">Exported</div><div class="metric" id="exported">0</div></div>
    <div class="card"><div class="label">URLs</div><div class="metric" id="urls">0</div></div>
    <div class="card"><div class="label">Native libs</div><div class="metric" id="native">0</div></div>
    <div class="card"><div class="label">Risk findings</div><div class="metric" id="risks">0</div></div>
  </div>

  <div class="modebar">
    <button class="modebtn" data-mode="/apk360">/apk360</button>
    <button class="modebtn" data-mode="/apkmanifest">/apkmanifest</button>
    <button class="modebtn" data-mode="/apkpermissions">/apkpermissions</button>
    <button class="modebtn" data-mode="/apkcomponents">/apkcomponents</button>
    <button class="modebtn" data-mode="/apkurls">/apkurls</button>
    <button class="modebtn" data-mode="/apkapi">/apkapi</button>
    <button class="modebtn" data-mode="/apkkeys">/apkkeys</button>
    <button class="modebtn" data-mode="/apkcerts">/apkcerts</button>
    <button class="modebtn" data-mode="/apknative">/apknative</button>
    <button class="modebtn" data-mode="/apkwebview">/apkwebview</button>
    <button class="modebtn" data-mode="/apkcrypto">/apkcrypto</button>
    <button class="modebtn" data-mode="/apkfiles">/apkfiles</button>
    <button class="modebtn" data-mode="/apkcode">/apkcode</button>
    <button class="modebtn" data-mode="/apkrisk">/apkrisk</button>
    <button class="modebtn" data-mode="/apktools">/apktools</button>
  </div>

  <div class="card">
    <div class="toolbar">
      <input id="search" placeholder="Search current APK view...">
      <select id="filter"><option value="">All</option></select>
    </div>
    <h2 id="title">APK overview</h2>
    <div class="list" id="list"></div>
    <pre id="pre" style="display:none"></pre>
    <div class="note" id="note"></div>
  </div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const $=id=>document.getElementById(id);
$('apkPath').textContent=D.summary?.apk||'';
$('sha').textContent='SHA-256 '+(D.summary?.sha256||'-');
$('pkg').textContent=D.summary?.package||'-';$('entries').textContent=D.summary?.entries||0;$('permissions').textContent=D.summary?.permissions||0;$('exported').textContent=D.summary?.exportedComponents||0;$('urls').textContent=D.summary?.urls||0;$('native').textContent=D.summary?.nativeLibraries||0;$('risks').textContent=D.summary?.riskFindings||0;
let MODE=__MODE__;

function add(title,meta='',body='',tags=[]){
  const d=document.createElement('div');d.className='item';
  const h=document.createElement('strong');h.textContent=title;d.appendChild(h);
  if(tags.length){const t=document.createElement('div');tags.forEach(x=>{const s=document.createElement('span');s.className='pill '+(x.cls||'');s.textContent=x.text; t.appendChild(s)});d.appendChild(t)}
  if(meta){const m=document.createElement('div');m.className='meta';m.textContent=meta;d.appendChild(m)}
  if(body){const b=document.createElement('div');b.textContent=body;d.appendChild(b)}
  $('list').appendChild(d);
}
function matches(x){
  const q=$('search').value.trim().toLowerCase(),f=$('filter').value;
  const txt=JSON.stringify(x).toLowerCase();
  return (!q||txt.includes(q))&&(!f||txt.includes(f.toLowerCase()));
}
function fillFilter(vals){
  const s=$('filter');while(s.options.length>1)s.remove(1);
  [...new Set(vals.filter(Boolean))].sort().forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;s.appendChild(o)})
}
function render(){
  $('list').replaceChildren();$('pre').style.display='none';$('pre').textContent='';$('note').textContent='';
  document.querySelectorAll('.modebtn').forEach(b=>b.classList.toggle('active',b.dataset.mode===MODE));
  let title='APK overview',filters=[];
  if(MODE==='/apkmanifest'){
    title='/apkmanifest — package / SDK / application manifest';
    add('Package',D.manifest?.tool||'manifest decoder',D.manifest?.package||'-');
    add('SDK','min '+(D.manifest?.minSdk||'-')+' · target '+(D.manifest?.targetSdk||'-'),'');
    Object.entries(D.manifest?.application||{}).forEach(([k,v])=>add('application:'+k,'',String(v)));
    $('pre').style.display='block';$('pre').textContent=D.manifest?.raw||D.manifest?.badging||'Decoded manifest unavailable; install Android SDK apkanalyzer/aapt or JADX/APKTool for richer manifest output.';
  }else if(MODE==='/apkpermissions'){
    title='/apkpermissions — declared Android permissions';
    filters=['sensitive','normal'];
    (D.permissions?.items||[]).filter(x=>matches(x)).forEach(p=>add(p,'',D.permissions?.sensitive?.includes(p)?'Sensitive permission — review necessity':'',D.permissions?.sensitive?.includes(p)?[{text:'SENSITIVE',cls:'warn'}]:[]));
  }else if(MODE==='/apkcomponents'){
    title='/apkcomponents — activities / services / receivers / providers';
    filters=['true','false','unspecified'];
    (D.components?.items||[]).filter(matches).forEach(x=>add(x.type+' · '+x.name,'exported='+x.exported,'',x.exported==='true'?[{text:'EXPORTED',cls:'warn'}]:[]));
  }else if(MODE==='/apkurls'){
    title='/apkurls — literal endpoints recovered from APK';
    filters=[...(D.urls?.items||[]).map(x=>x.scheme)];
    (D.urls?.items||[]).filter(matches).forEach(x=>add(x.url,x.entry+' @ '+x.offset,(x.host||'')));
  }else if(MODE==='/apkapi'){
    title='/apkapi — API/endpoint path references';
    (D.api?.items||[]).filter(matches).forEach(x=>add(x.preview,x.entry+' @ '+x.offset,''));
  }else if(MODE==='/apkkeys'){
    title='/apkkeys — redacted secret/key references';
    (D.keys?.items||[]).filter(matches).forEach(x=>add(x.name||'secret-like',x.entry+' @ '+x.offset,'Masked: '+(x.masked||'<redacted>'),[{text:'REDACTED',cls:'warn'}]));
    $('note').textContent=D.keys?.note||'Full secret values are not displayed.';
  }else if(MODE==='/apkcerts'){
    title='/apkcerts — signing/certificate evidence';
    (D.certs?.zipEntries||[]).filter(matches).forEach(x=>add(x.path,x.bytes+' bytes · CRC '+x.crc,''));
    $('pre').style.display='block';$('pre').textContent=D.certs?.signerOutput||D.certs?.signerError||'No signing-certificate tool available. Install apksigner or keytool for certificate metadata.';
  }else if(MODE==='/apknative'){
    title='/apknative — ABI and native .so libraries';
    filters=Object.keys(D.native?.libraries||{});
    Object.entries(D.native?.libraries||{}).forEach(([abi,items])=>items.filter(matches).forEach(x=>add(x.name,abi,x.path+' · '+x.bytes+' bytes')));
  }else if(MODE==='/apkwebview'){
    title='/apkwebview — WebView / JavaScript bridge references';
    (D.webview?.items||[]).filter(matches).forEach(x=>add('WebView reference',x.entry+' @ '+x.offset,x.preview||''));
  }else if(MODE==='/apkcrypto'){
    title='/apkcrypto — crypto/hash/key-store references';
    (D.crypto?.items||[]).filter(matches).forEach(x=>add('Crypto reference',x.entry+' @ '+x.offset,x.preview||''));
  }else if(MODE==='/apkfiles'){
    title='/apkfiles — full APK ZIP inventory';
    filters=Object.keys(D.files?.extensions||{});
    (D.files?.items||[]).filter(matches).forEach(x=>add(x.path,(x.extension||'[none]')+' · '+x.bytes+' bytes','compressed '+x.compressed+' · CRC '+x.crc));
  }else if(MODE==='/apkcode'){
    title='/apkcode — optional JADX decompilation status';
    add('JADX',D.decompile?.tool||'unavailable',D.decompile?.requested?(D.decompile?.ok?'Decompile succeeded':'Decompile requested but failed'):'Run APK scanner with -Decompile to enable.');
    if(D.extractedSummary?.files)add('Extracted source files','',String(D.extractedSummary.files));
    Object.entries(D.extractedSummary?.extensions||{}).forEach(([k,v])=>add(k,'',String(v)));
    $('note').textContent='Lola does not bypass code protection. Decompiled output is for authorized static review.';
  }else if(MODE==='/apkrisk'){
    title='/apkrisk — review findings';
    filters=['ERROR','WARNING','INFO'];
    (D.risk?.items||[]).filter(matches).forEach(x=>add(x.area+' · '+x.message,typeof x.detail==='string'?x.detail:JSON.stringify(x.detail),'',[{text:x.severity,cls:x.severity==='ERROR'?'bad':x.severity==='WARNING'?'warn':'ok'}]));
  }else if(MODE==='/apktools'){
    title='/apktools — local analyzer capability';
    Object.entries(D.tools||{}).forEach(([k,v])=>add(k,'',v?'Available':'Not found',[{text:v?'READY':'MISSING',cls:v?'ok':'warn'}]));
  }else{
    title='/apk360 — APK full surface';
    const s=D.summary||{};
    [['Package',s.package],['SHA-256',s.sha256],['Size',s.bytes+' bytes'],['SDK','min '+(s.minSdk||'-')+' / target '+(s.targetSdk||'-')],['DEX files',s.dexFiles],['ABIs',JSON.stringify(s.abis||{})],['Permissions',s.permissions],['Exported components',s.exportedComponents],['URLs',s.urls],['API refs',s.apiRefs],['Secret refs',s.secretRefs],['WebView refs',s.webViewRefs],['Crypto refs',s.cryptoRefs],['Native libs',s.nativeLibraries],['Risk findings',s.riskFindings]].forEach(x=>add(x[0],'',String(x[1]??'-')));
    (D.risk?.items||[]).slice(0,50).forEach(x=>add('Risk · '+x.area,x.message,typeof x.detail==='string'?x.detail:JSON.stringify(x.detail),[{text:x.severity,cls:x.severity==='ERROR'?'bad':x.severity==='WARNING'?'warn':'ok'}]));
  }
  $('title').textContent=title;fillFilter(filters);
  if(!$('list').children.length&&$('pre').style.display==='none')$('list').innerHTML='<div class="item muted">No matching APK evidence.</div>';
}
document.querySelectorAll('.modebtn').forEach(b=>b.onclick=()=>{MODE=b.dataset.mode;$('filter').value='';render()});
$('search').oninput=render;$('filter').onchange=render;render();
</script></body></html>""".replace("__DATA__",blob).replace("__MODE__",json.dumps(args.mode))
    Path(args.output).write_text(page,encoding="utf-8")
    print(f"APK report written: {Path(args.output).resolve()}")

if __name__=="__main__":
    main()

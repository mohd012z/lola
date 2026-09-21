#!/usr/bin/env python3
import argparse, json, re, shutil, hashlib
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

CERT_EXTS={".crt",".cer",".pem",".der"}
PRIVATE_EXTS={".key",".p12",".pfx",".jks",".keystore"}
API_HINT=re.compile(r"(?i)(/api(?:/|$)|api[_-]?(?:url|base|endpoint|host)|fetch\s*\(|axios\.|XMLHttpRequest|WebSocket|graphql|grpc|retrofit|okhttp)")
LOG_HINT=re.compile(r"(?i)(console\.(log|warn|error|debug)|logger\.|logging\.|log4j|slf4j|winston|pino|bunyan|sentry|datadog|newrelic)")
LOG_HIDE_HINT=re.compile(r"(?i)(disable(?:d)?[_ -]?log|suppress[_ -]?log|quiet[_ -]?mode|no[_ -]?log|clear(?:Logs?|History)|delete(?:Logs?|History)|truncate(?:Logs?|History)|logger\.disabled|logging\.disable|console\.log\s*=\s*(?:\(\)\s*=>|function\s*\(\)\s*\{\s*\}))")
HIDDEN_TRACE_HINT=re.compile(r"(?i)(incognito|private[_ -]?mode|stealth|hidden[_ -]?mode|invisible|headless|background[_ -]?mode|display\s*:\s*none|visibility\s*:\s*hidden|aria-hidden)")
HIDDEN_MODE_HINT=re.compile(r"(?i)(hiddenMode|hideMode|stealthMode|privateMode|incognitoMode|silentMode|backgroundMode)")
ANON_HINTS={
    "public-ip-discovery": re.compile(r"(?i)(api\.ipify\.org|ipinfo\.io|ifconfig\.me|icanhazip\.com|checkip\.amazonaws\.com|ipapi\.co|ip-api\.com|whatismyip)"),
    "telemetry-tracking": re.compile(r"(?i)(google-analytics|googletagmanager|gtag\s*\(|mixpanel|segment\.|amplitude|appsflyer|adjust\.|sentry|datadog|newrelic|matomo|plausible|posthog|clarity|hotjar|fbq\s*\()"),
    "fingerprinting": re.compile(r"(?i)(fingerprintjs|fingerprint2|clientjs|canvas\.toDataURL|getImageData\s*\(|WEBGL_debug_renderer_info|device fingerprint)"),
    "device-account-id": re.compile(r"(?i)(ANDROID_ID|AdvertisingIdClient|advertisingIdentifier|identifierForVendor|device[_-]?id|user[_-]?id|client[_-]?id|visitor[_-]?id|anonymous[_-]?id|distinct[_-]?id)"),
    "webrtc-local-network": re.compile(r"(?i)(RTCPeerConnection|icecandidate|candidate\.candidate|networkInterfaces\s*\()"),
}
ROUTE_RE=re.compile(r"""(?i)\b(?:app|router|server)\.(get|post|put|patch|delete|options|head|use)\s*\(\s*["']([^"']+)["']""")
URL_RE=re.compile(r"""(?i)\b(?:https?|wss?|ftp|ftps|sftp|ssh|mqtts?|amqps?|grpc|grpcs)://[^\s"'<>]+""")
SECRET_NAME=re.compile(r"(?i)(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|credential)")
PRIVATE_KEY_BLOCK=re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]{0,50000}?-----END [A-Z0-9 ]*PRIVATE KEY-----")
SECRET_ASSIGN=re.compile(r"""(?ix)\b(?P<n>[A-Za-z_][A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|private[_-]?key|credential)[A-Za-z0-9_.-]*)\s*[:=]\s*(?P<q>["'])(?P<v>[^"'\r\n]{1,1000})(?P=q)""")

def read_json(path, default):
    p=Path(path)
    if not p.exists(): return default
    try:return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:return default

def sha256_file(path):
    h=hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
        return h.hexdigest()
    except Exception:return ""

def mask(v):
    if not v:return "<redacted>"
    if len(v)<=4:return "<redacted>"
    return v[:2]+"*"*min(max(len(v)-4,4),16)+v[-2:]+f" ({len(v)} chars)"

def redact(t):
    t=PRIVATE_KEY_BLOCK.sub("<PRIVATE_KEY_REDACTED>",t)
    return SECRET_ASSIGN.sub(lambda m:f'{m.group("n")}={m.group("q")}{mask(m.group("v"))}{m.group("q")}',t)

def line_no(t,pos):return t.count("\n",0,pos)+1

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",default="target-manifest.json")
    ap.add_argument("--urls",default="url-report.json")
    ap.add_argument("--code",default="code-analysis.json")
    ap.add_argument("--output",default="preflight-analysis.json")
    ap.add_argument("--cert-dir",default=".lola-preflight/certs")
    ap.add_argument("--snapshot-dir",default=".lola-preflight/code")
    ap.add_argument("--copy-certs",action="store_true")
    ap.add_argument("--capture-code",action="store_true")
    args=ap.parse_args()

    manifest=read_json(args.manifest,{"files":[]})
    urls=read_json(args.urls,{"urls":[]})
    code=read_json(args.code,{})
    extraction=(code.get("extraction") or {})
    files=manifest.get("files",[]) or []

    apis=[]; hidden_traces=[]; hide_modes=[]; hide_logs=[]; keys=[]; certs=[]; ipmirror=[]; anonymous=[]
    route_items=list(extraction.get("routes",[]) or [])
    url_items=list(urls.get("urls",[]) or [])

    cert_dir=Path(args.cert_dir); snap_dir=Path(args.snapshot_dir)
    copied_certs=[]; snapshot_files=[]

    for mf in files:
        p=Path(mf.get("path",""))
        if not p.is_file():continue
        ext=p.suffix.lower()
        # cert/key metadata
        if ext in CERT_EXTS|PRIVATE_EXTS:
            item={"path":str(p),"extension":ext,"bytes":mf.get("bytes",p.stat().st_size),"sha256":mf.get("sha256") or sha256_file(p)}
            if ext in PRIVATE_EXTS:
                item["kind"]="private-key-container"
                item["copied"]=False
                keys.append({**item,"name":p.name,"masked":"<private key/container not copied>"})
            else:
                item["kind"]="public-certificate-or-pem"
                certs.append(item)
                if args.copy_certs and ext in {".crt",".cer",".der"}:
                    cert_dir.mkdir(parents=True,exist_ok=True)
                    dest=cert_dir/(p.name+"."+item["sha256"][:12])
                    try:
                        shutil.copy2(p,dest)
                        copied_certs.append({"source":str(p),"copy":str(dest),"sha256":item["sha256"]})
                    except Exception as e:
                        copied_certs.append({"source":str(p),"error":str(e),"sha256":item["sha256"]})

        try:
            if p.stat().st_size>3*1024*1024:continue
            text=p.read_text(encoding="utf-8",errors="ignore")
        except Exception:continue
        lines=text.splitlines()

        # optional full redacted source snapshot
        if args.capture_code:
            rel=Path(mf.get("name") or p.name)
            dest=snap_dir/(mf.get("sha256","")[:12]+"_"+p.name)
            snap_dir.mkdir(parents=True,exist_ok=True)
            try:
                dest.write_text(redact(text),encoding="utf-8")
                snapshot_files.append({"source":str(p),"copy":str(dest),"sha256":mf.get("sha256") or sha256_file(p),"lines":len(lines)})
            except Exception as e:
                snapshot_files.append({"source":str(p),"error":str(e)})

        for pat,kind,bucket in [(API_HINT,"api",apis),(HIDDEN_TRACE_HINT,"hidden-trace",hidden_traces),(HIDDEN_MODE_HINT,"hidden-mode",hide_modes),(LOG_HIDE_HINT,"log-suppression",hide_logs)]:
            for m in pat.finditer(text):
                ln=line_no(text,m.start())
                line=lines[ln-1] if 0<ln<=len(lines) else m.group(0)
                bucket.append({"path":str(p),"line":ln,"kind":kind,"preview":redact(line.strip())[:1000]})

        for kind,pat in ANON_HINTS.items():
            for m in pat.finditer(text):
                ln=line_no(text,m.start())
                line=lines[ln-1] if 0<ln<=len(lines) else m.group(0)
                anonymous.append({"path":str(p),"line":ln,"kind":kind,"preview":redact(line.strip())[:1000]})

        # route/API extraction not covered by analyze-code
        for m in ROUTE_RE.finditer(text):
            r={"path":str(p),"line":line_no(text,m.start()),"method":m.group(1).upper(),"route":m.group(2)}
            if r not in route_items: route_items.append(r)

        # secret/key references, redacted only
        for i,line in enumerate(lines,1):
            sm=SECRET_NAME.search(line)
            if sm and len(keys)<8000:
                mm=SECRET_ASSIGN.search(line)
                keys.append({"path":str(p),"line":i,"name":sm.group(0),"masked":mask(mm.group("v")) if mm else "<value not collected>"})

    # URL / IP mirror: reflect app destinations, not user geolocation
    for u in url_items:
        ips=u.get("resolvedIps",[]) or []
        ipmirror.append({
            "sourceUrl":u.get("sourceUrl",""),"finalUrl":u.get("finalUrl",""),
            "host":u.get("host",""),"resolvedIps":ips,
            "destinationClass":u.get("destinationClass",""),"status":u.get("status"),
            "occurrences":u.get("occurrences",[])
        })

    # logical map
    nodes={};edges=[]
    def node(i,label,kind):
        nodes.setdefault(i,{"id":i,"label":label,"kind":kind})
    def edge(a,b,label):edges.append({"from":a,"to":b,"label":label})
    for i,u in enumerate(url_items):
        src=u.get("sourceUrl",""); host=u.get("host","") or (urlsplit(src).hostname if src else "")
        uid=f"url:{i}";node(uid,src or "[url]","url")
        if host:
            hid=f"host:{host}";node(hid,host,"host");edge(uid,hid,"host")
            for ip in u.get("resolvedIps",[]) or []:
                iid=f"ip:{ip}";node(iid,ip,"ip");edge(hid,iid,"dns")
        for occ in u.get("occurrences",[]) or []:
            p=occ.get("path","")
            if p:
                fid=f"file:{p}";node(fid,p,"file");edge(fid,uid,f"line {occ.get('line','?')}")
    for i,r in enumerate(route_items):
        rid=f"route:{i}";node(rid,f"{r.get('method','')} {r.get('route','')}".strip(),"route")
        if r.get("path"):
            fid=f"file:{r['path']}";node(fid,r["path"],"file");edge(fid,rid,f"line {r.get('line','?')}")

    out={
        "phase":"before-semgrep",
        "target":manifest.get("target",""),
        "summary":{
            "files":len(files),"urls":len(url_items),"routes":len(route_items),"apiRefs":len(apis),
            "keyRefs":len(keys),"certs":len(certs),"hiddenTraces":len(hidden_traces),
            "hiddenModes":len(hide_modes),"hideLogRefs":len(hide_logs),"ipMirror":len(ipmirror),
            "anonymousPrivacyRefs":len(anonymous),
            "capturedCodeFiles":len(snapshot_files),"copiedPublicCerts":len([x for x in copied_certs if x.get("copy")])
        },
        "viewextraction":{
            "imports":extraction.get("imports",[]),"functions":extraction.get("functions",[]),
            "classes":extraction.get("classes",[]),"environment":extraction.get("environment",[]),
            "routes":route_items
        },
        "viewurls":{"items":url_items},
        "map":{"nodes":list(nodes.values()),"edges":edges},
        "routes":{"items":route_items},
        "api":{"items":apis},
        "keys":{"items":keys,"redacted":True,"note":"Values are masked or not collected."},
        "anonymous":{"items":anonymous,"counts":dict(Counter(x["kind"] for x in anonymous)),"note":"Pre-Semgrep privacy/identity exposure inventory; it does not conceal identity or bypass tracking/security controls."},
        "hiddentraces":{"items":hidden_traces,"note":"Detection-only: this mode identifies hidden/stealth-like code patterns; it does not enable concealment."},
        "hidemodes":{"items":hide_modes,"note":"Detection-only: identifies hidden/private/silent mode references."},
        "hidelog":{"items":hide_logs,"note":"Detection-only: identifies logging suppression/clearing code. Lola does not erase application, OS, or security logs."},
        "ipmirror":{"items":ipmirror,"note":"Mirrors application destination IP resolution; not a device-geolocation feature."},
        "certs":{"items":certs,"copies":copied_certs,"privateKeyCopies":False},
        "capture":{"enabled":args.capture_code,"files":snapshot_files,"redacted":True}
    }
    Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Preflight analysis written: {Path(args.output).resolve()}")

if __name__=="__main__":
    main()

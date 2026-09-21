#!/usr/bin/env python3
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

MAX_ENTRY_TEXT=4*1024*1024
MAX_STRINGS_PER_ENTRY=5000
PRINTABLE_RE=re.compile(rb"[\x20-\x7e]{5,}")
URL_RE=re.compile(r"""(?i)\b(?:https?|wss?|ftp|ftps|sftp|ssh|mqtts?|amqps?|grpc|grpcs)://[^\s"'<>\\]+""")
API_RE=re.compile(r"""(?i)(?:https?://[^\s"'<>]+)?/(?:api|v\d+|graphql|oauth|auth|login|token|config|stream|media|video|playlist|m3u8)(?:/|[?&\s"'<>]|$)""")
SECRET_NAME_RE=re.compile(r"(?i)(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|bearer|credential)")
SECRET_ASSIGN_RE=re.compile(r"""(?ix)\b(?P<n>[A-Za-z_][A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|credential)[A-Za-z0-9_.-]*)\s*[:=]\s*(?P<q>["'])(?P<v>[^"'\r\n]{1,1000})(?P=q)""")
PROVIDER_TOKEN_RE=re.compile(r"(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})")
PRIVATE_KEY_RE=re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]{0,50000}?-----END [A-Z0-9 ]*PRIVATE KEY-----")
WEBVIEW_RE=re.compile(r"(?i)(WebView|setJavaScriptEnabled|addJavascriptInterface|setAllowFileAccess|setAllowContentAccess|setDomStorageEnabled|setMixedContentMode|setWebContentsDebuggingEnabled|loadUrl\s*\(|evaluateJavascript)")
CRYPTO_RE=re.compile(r"(?i)(AES/(?:GCM|CBC|ECB)|Cipher\.getInstance|SecretKey|KeyStore|PBKDF2|scrypt|argon2|bcrypt|SHA-?1|SHA-?256|SHA-?512|MD5|RSA|ECIES|ChaCha20|GCMParameterSpec)")
ROOT_DEBUG_RE=re.compile(r"(?i)(rooted|magisk|su\b|busybox|frida|xposed|debuggable|testOnly|allowBackup|usesCleartextTraffic|networkSecurityConfig)")
PERM_RE=re.compile(r"android\.permission\.[A-Z0-9_.]+")
EXPORTED_RE=re.compile(r"""<(?P<t>activity|activity-alias|service|receiver|provider)\b[^>]*?android:name=["'](?P<n>[^"']+)["'][^>]*?(?:android:exported=["'](?P<e>true|false)["'])?[^>]*>""",re.I|re.S)
SDK_RE=re.compile(r"""<uses-sdk\b[^>]*?(?:android:minSdkVersion=["'](?P<min>[^"']+)["'])?[^>]*?(?:android:targetSdkVersion=["'](?P<target>[^"']+)["'])?[^>]*/?>""",re.I|re.S)
PKG_RE=re.compile(r"""<manifest\b[^>]*?\bpackage=["']([^"']+)["']""",re.I)
APP_ATTR_RE=re.compile(r"""<application\b([^>]*)>""",re.I|re.S)
ATTR_RE=re.compile(r"""android:([A-Za-z0-9_]+)=["']([^"']*)["']""")

HIGH_RISK_PERMS={
 "android.permission.READ_SMS","android.permission.RECEIVE_SMS","android.permission.SEND_SMS",
 "android.permission.READ_CALL_LOG","android.permission.WRITE_CALL_LOG","android.permission.READ_CONTACTS",
 "android.permission.WRITE_CONTACTS","android.permission.RECORD_AUDIO","android.permission.CAMERA",
 "android.permission.ACCESS_FINE_LOCATION","android.permission.ACCESS_BACKGROUND_LOCATION",
 "android.permission.READ_PHONE_STATE","android.permission.READ_PHONE_NUMBERS","android.permission.REQUEST_INSTALL_PACKAGES",
 "android.permission.MANAGE_EXTERNAL_STORAGE","android.permission.QUERY_ALL_PACKAGES","android.permission.SYSTEM_ALERT_WINDOW"
}

TEXT_EXTS={".xml",".json",".txt",".html",".htm",".js",".css",".properties",".ini",".cfg",".conf",".yaml",".yml",".md",".csv",".m3u8",".mpd"}

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for ch in iter(lambda:f.read(1024*1024),b""):h.update(ch)
    return h.hexdigest()

def mask(v):
    if not v:return "<redacted>"
    n=len(v)
    if n<=4:return "<redacted>"
    return v[:2]+"*"*min(max(n-4,4),16)+v[-2:]+f" ({n} chars)"

def redact(t):
    t=PRIVATE_KEY_RE.sub("<PRIVATE_KEY_REDACTED>",t)
    t=PROVIDER_TOKEN_RE.sub(lambda m:mask(m.group(0)),t)
    return SECRET_ASSIGN_RE.sub(lambda m:f'{m.group("n")}={m.group("q")}{mask(m.group("v"))}{m.group("q")}',t)

def run(cmd,timeout=45):
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,errors="ignore")
        return {"ok":p.returncode==0,"code":p.returncode,"stdout":p.stdout[-250000:],"stderr":p.stderr[-50000:]}
    except Exception as e:return {"ok":False,"error":str(e),"stdout":"","stderr":""}

def tool(name): return shutil.which(name)

def decode_manifest(apk):
    attempts=[]
    if tool("apkanalyzer"):
        r=run(["apkanalyzer","manifest","print",str(apk)])
        attempts.append(("apkanalyzer",r))
        if r.get("ok") and "<manifest" in r.get("stdout",""):return r["stdout"],"apkanalyzer",attempts
    if tool("aapt2"):
        r=run(["aapt2","dump","xmltree",str(apk),"AndroidManifest.xml"])
        attempts.append(("aapt2",r))
    if tool("aapt"):
        r=run(["aapt","dump","xmltree",str(apk),"AndroidManifest.xml"])
        attempts.append(("aapt",r))
    if tool("jadx"):
        td=Path(tempfile.mkdtemp(prefix="lola_manifest_"))
        try:
            r=run(["jadx","--no-src","--no-res","-d",str(td),str(apk)],120)
            attempts.append(("jadx",r))
        finally:
            shutil.rmtree(td,ignore_errors=True)
    return "","unavailable",attempts

def extract_aapt_badging(apk):
    for n in ("aapt2","aapt"):
        if tool(n):
            r=run([n,"dump","badging",str(apk)])
            if r.get("ok"): return r.get("stdout",""),n
    return "","unavailable"

def signer_info(apk):
    if tool("apksigner"):
        r=run(["apksigner","verify","--verbose","--print-certs",str(apk)])
        return {"tool":"apksigner",**r}
    if tool("keytool"):
        r=run(["keytool","-printcert","-jarfile",str(apk)])
        return {"tool":"keytool",**r}
    return {"tool":"unavailable","ok":False,"stdout":"","stderr":""}

def collect_strings(data):
    out=[]
    for m in PRINTABLE_RE.finditer(data):
        try:s=m.group(0).decode("utf-8","ignore")
        except Exception:continue
        if s: out.append((m.start(),s))
        if len(out)>=MAX_STRINGS_PER_ENTRY:break
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("apk")
    ap.add_argument("--output",default="apk-analysis.json")
    ap.add_argument("--extract-dir",default=".lola-apk/decompiled")
    ap.add_argument("--decompile",action="store_true")
    ap.add_argument("--keep-extracted",action="store_true")
    args=ap.parse_args()
    apk=Path(args.apk).resolve()
    if not apk.exists() or apk.suffix.lower()!=".apk":raise SystemExit("Target must be an existing .apk file")
    if not zipfile.is_zipfile(apk):raise SystemExit("Target is not a valid ZIP/APK container")

    files=[]; urls=[]; api_refs=[]; secret_refs=[]; webview=[]; crypto=[]; indicators=[]
    native=defaultdict(list); dex=[]; assets=[]; cert_entries=[]; abis=Counter()
    ext_counts=Counter(); total_uncompressed=0
    with zipfile.ZipFile(apk,"r") as z:
        for zi in z.infolist():
            p=zi.filename
            ext=Path(p).suffix.lower()
            ext_counts[ext or "[none]"]+=1;total_uncompressed+=zi.file_size
            item={"path":p,"compressed":zi.compress_size,"bytes":zi.file_size,"crc":f"{zi.CRC:08x}","extension":ext}
            files.append(item)
            if re.match(r"classes(?:\d+)?\.dex$",Path(p).name): dex.append(item)
            if p.startswith("assets/"): assets.append(item)
            if p.upper().startswith("META-INF/") and ext in {".rsa",".dsa",".ec",".sf",".mf"}:cert_entries.append(item)
            m=re.match(r"lib/([^/]+)/(.+\.so)$",p)
            if m:
                abi,name=m.groups();abis[abi]+=1;native[abi].append({"path":p,"name":name,"bytes":zi.file_size})
            # Only inspect bounded entries plus DEX strings.
            if zi.file_size==0 or zi.file_size>MAX_ENTRY_TEXT and ext!=".dex": continue
            try:data=z.read(zi)
            except Exception:continue
            text=""
            if ext in TEXT_EXTS:
                text=data[:MAX_ENTRY_TEXT].decode("utf-8","ignore")
                strings=[(0,text)]
            else:
                strings=collect_strings(data)
            for off,s in strings:
                rs=redact(s)
                for murl in URL_RE.finditer(s):
                    raw=murl.group(0)
                    urls.append({"entry":p,"offset":off+murl.start(),"url":redact(raw),"host":urlsplit(raw).hostname or "","scheme":urlsplit(raw).scheme})
                for ma in API_RE.finditer(s):
                    api_refs.append({"entry":p,"offset":off+ma.start(),"preview":redact(ma.group(0))[:600]})
                if SECRET_NAME_RE.search(s) or PROVIDER_TOKEN_RE.search(s) or PRIVATE_KEY_RE.search(s):
                    mm=SECRET_ASSIGN_RE.search(s)
                    secret_refs.append({"entry":p,"offset":off,"name":(mm.group("n") if mm else (SECRET_NAME_RE.search(s).group(0) if SECRET_NAME_RE.search(s) else "secret-like")),"masked":mask(mm.group("v")) if mm else "<value not collected>"})
                if WEBVIEW_RE.search(s): webview.append({"entry":p,"offset":off,"preview":rs[:900]})
                if CRYPTO_RE.search(s): crypto.append({"entry":p,"offset":off,"preview":rs[:900]})
                if ROOT_DEBUG_RE.search(s): indicators.append({"entry":p,"offset":off,"preview":rs[:900]})

    manifest_xml,manifest_tool,manifest_attempts=decode_manifest(apk)
    badging,badging_tool=extract_aapt_badging(apk)
    signer=signer_info(apk)

    package="";min_sdk="";target_sdk="";permissions=[];components=[];app_attrs={}
    if manifest_xml:
        pm=PKG_RE.search(manifest_xml); package=pm.group(1) if pm else ""
        sm=SDK_RE.search(manifest_xml)
        if sm:min_sdk=sm.group("min") or "";target_sdk=sm.group("target") or ""
        permissions=sorted(set(PERM_RE.findall(manifest_xml)))
        for m in EXPORTED_RE.finditer(manifest_xml):
            components.append({"type":m.group("t"),"name":m.group("n"),"exported":m.group("e") or "unspecified"})
        am=APP_ATTR_RE.search(manifest_xml)
        if am: app_attrs={k:v for k,v in ATTR_RE.findall(am.group(1))}
    if badging:
        if not package:
            m=re.search(r"package: name='([^']+)'",badging);package=m.group(1) if m else package
        if not min_sdk:
            m=re.search(r"sdkVersion:'([^']+)'",badging);min_sdk=m.group(1) if m else min_sdk
        if not target_sdk:
            m=re.search(r"targetSdkVersion:'([^']+)'",badging);target_sdk=m.group(1) if m else target_sdk
        permissions=sorted(set(permissions+re.findall(r"uses-permission: name='([^']+)'",badging)))

    decompile={"requested":args.decompile,"tool":"jadx" if tool("jadx") else "unavailable","path":"","ok":False}
    extracted_summary={}
    if args.decompile and tool("jadx"):
        outdir=Path(args.extract_dir).resolve()
        if outdir.exists():shutil.rmtree(outdir,ignore_errors=True)
        r=run(["jadx","-d",str(outdir),str(apk)],240)
        decompile.update({"ok":r.get("ok",False),"path":str(outdir),"stderr":r.get("stderr","")[-5000:]})
        if outdir.exists():
            counts=Counter();count=0
            for p in outdir.rglob("*"):
                if p.is_file():
                    counts[p.suffix.lower() or "[none]"]+=1;count+=1
            extracted_summary={"files":count,"extensions":dict(counts)}
        if not args.keep_extracted and outdir.exists():
            shutil.rmtree(outdir,ignore_errors=True)
            decompile["path"]="";decompile["cleaned"]=True

    exported=[x for x in components if x["exported"]=="true"]
    risk=[]
    for p in permissions:
        if p in HIGH_RISK_PERMS:risk.append({"severity":"WARNING","area":"permission","message":"Sensitive permission declared","detail":p})
    for x in exported:
        risk.append({"severity":"WARNING","area":"exported-component","message":"Exported Android component requires review","detail":x})
    if app_attrs.get("usesCleartextTraffic","").lower()=="true":risk.append({"severity":"WARNING","area":"network","message":"Cleartext traffic enabled","detail":"android:usesCleartextTraffic=true"})
    if app_attrs.get("debuggable","").lower()=="true":risk.append({"severity":"ERROR","area":"build","message":"Application is debuggable","detail":"android:debuggable=true"})
    if app_attrs.get("allowBackup","").lower()=="true":risk.append({"severity":"INFO","area":"backup","message":"Application backup is enabled","detail":"android:allowBackup=true"})
    if any("setWebContentsDebuggingEnabled" in x["preview"] for x in webview):risk.append({"severity":"WARNING","area":"webview","message":"WebView debugging reference found","detail":"Review release-build behavior"})
    if any(re.search(r"(?i)AES/ECB|MD5|SHA-?1",x["preview"]) for x in crypto):risk.append({"severity":"WARNING","area":"crypto","message":"Legacy/weak crypto reference found","detail":"Review crypto findings"})
    if secret_refs:risk.append({"severity":"WARNING","area":"secrets","message":"Secret-like references found in APK strings/resources","detail":f"{len(secret_refs)} references; values redacted"})

    tools={n:bool(tool(n)) for n in ["apkanalyzer","aapt2","aapt","apksigner","keytool","jadx","apktool"]}
    summary={
        "apk":str(apk),"sha256":sha256_file(apk),"bytes":apk.stat().st_size,
        "entries":len(files),"uncompressedBytes":total_uncompressed,"package":package,
        "minSdk":min_sdk,"targetSdk":target_sdk,"permissions":len(permissions),
        "exportedComponents":len(exported),"dexFiles":len(dex),"nativeLibraries":sum(len(v) for v in native.values()),
        "abis":dict(abis),"urls":len(urls),"apiRefs":len(api_refs),"secretRefs":len(secret_refs),
        "webViewRefs":len(webview),"cryptoRefs":len(crypto),"riskFindings":len(risk)
    }
    out={
      "summary":summary,"tools":tools,
      "manifest":{"tool":manifest_tool,"package":package,"minSdk":min_sdk,"targetSdk":target_sdk,"application":app_attrs,"raw":manifest_xml[:300000] if manifest_xml else "","badgingTool":badging_tool,"badging":badging[:120000]},
      "permissions":{"items":permissions,"sensitive":[p for p in permissions if p in HIGH_RISK_PERMS]},
      "components":{"items":components,"exported":exported},
      "files":{"items":files,"extensions":dict(ext_counts),"assets":assets,"dex":dex},
      "native":{"abis":dict(abis),"libraries":dict(native)},
      "urls":{"items":urls},
      "api":{"items":api_refs},
      "keys":{"items":secret_refs,"redacted":True,"note":"Full secret values are not collected."},
      "certs":{"zipEntries":cert_entries,"signerTool":signer.get("tool"),"signerOutput":redact(signer.get("stdout",""))[:200000],"signerError":signer.get("stderr","")[:20000]},
      "webview":{"items":webview},
      "crypto":{"items":crypto},
      "indicators":{"items":indicators},
      "decompile":decompile,"extractedSummary":extracted_summary,
      "risk":{"items":risk},
      "manifestAttempts":[{"tool":n,"ok":r.get("ok",False),"error":r.get("error") or r.get("stderr","")[-1000:]} for n,r in manifest_attempts]
    }
    Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"APK analysis written: {Path(args.output).resolve()}")

if __name__=="__main__":
    main()

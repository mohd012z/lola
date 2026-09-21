#!/usr/bin/env python3
"""Build/search a redacted Android APK code-reader library."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from urllib.parse import urlsplit
from pathlib import Path
from typing import Any

MAX_TEXT_ENTRY = 512 * 1024
MAX_RESOURCE_ITEMS = 1200
MAX_DEX_STRINGS_PER_DEX = 2500
MAX_SOURCE_FILES = 2500
MAX_SOURCE_BYTES = 512 * 1024
MAX_SOURCE_PREVIEW = 24000
PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{6,}")
SECRET_ASSIGN_RE = re.compile(
    r"""(?ix)\b(?P<n>[A-Za-z_][A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|credential)[A-Za-z0-9_.-]*)\s*[:=]\s*(?P<q>["'])(?P<v>[^"'\r\n]{1,1000})(?P=q)"""
)
PROVIDER_TOKEN_RE = re.compile(r"(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]{0,50000}?-----END [A-Z0-9 ]*PRIVATE KEY-----")
CLASS_RE = re.compile(r"(?m)^\s*(?:public\s+|private\s+|protected\s+|internal\s+|abstract\s+|final\s+)*(?:class|interface|enum|object)\s+([A-Za-z_$][\w$]*)")
METHOD_RE = re.compile(r"(?m)^\s*(?:public|private|protected|internal|static|final|synchronized|native|abstract|suspend|override|\s)+[\w<>,?.\[\]$]+\s+([A-Za-z_$][\w$]*)\s*\(")
ANDROID_REF_RE = re.compile(r"(?i)\b(Activity|Service|BroadcastReceiver|ContentProvider|Intent|WebView|Context|SharedPreferences|RoomDatabase|SQLiteDatabase|Retrofit|OkHttpClient|WorkManager|Firebase|LocationManager|BiometricPrompt|KeyStore)\b")
STRING_LITERAL_RE = re.compile(r'''(?s)(?:"([^"\n\r]{4,220})"|'([^'\n\r]{4,220})')''')
BILLING_PATTERNS = {
    "payment": re.compile(r"(?i)\b(BillingClient|BillingFlowParams|launchBillingFlow|ProductDetails|Purchase|one[- ]time product|in[- ]app|IAB|billing)\b"),
    "subscribes": re.compile(r"(?i)\b(subscription|subs|basePlan|offerToken|ReplacementMode|renew|entitlement|queryPurchasesAsync|ProductType\.SUBS)\b"),
    "verify": re.compile(r"(?i)\b(verify|verification|purchaseState|PURCHASED|PENDING|isAcknowledged|acknowledgePurchase|signature|backend|server)\b"),
    "callback": re.compile(r"(?i)\b(PurchasesUpdatedListener|onPurchasesUpdated|onProductDetailsResponse|onBillingSetupFinished|onBillingServiceDisconnected|listener|callback)\b"),
    "fallback": re.compile(r"(?i)\b(fallback|retry|reconnect|backoff|SERVICE_DISCONNECTED|timeout|catch|exception|failed|failure|default)\b"),
    "recheck": re.compile(r"(?i)\b(queryPurchasesAsync|queryProductDetailsAsync|restore|refresh|resume|recheck|re-query|reconnect|onResume)\b"),
}

TEXT_EXTS = {
    ".xml",".json",".txt",".html",".htm",".js",".css",".properties",".ini",".cfg",
    ".conf",".yaml",".yml",".md",".csv",".m3u8",".mpd",".smali",".java",".kt",
    ".gradle",".kts",".pro"
}
SOURCE_EXTS = {".java",".kt",".smali",".xml",".json",".js",".html",".properties",".gradle",".kts",".pro"}

def mask(v: str) -> str:
    if not v or len(v) <= 4:
        return "<redacted>"
    return v[:2] + "*" * min(max(len(v)-4,4),16) + v[-2:] + f" ({len(v)} chars)"

def redact(text: str) -> str:
    text = PRIVATE_KEY_RE.sub("<PRIVATE_KEY_REDACTED>", text)
    text = PROVIDER_TOKEN_RE.sub(lambda m: mask(m.group(0)), text)
    return SECRET_ASSIGN_RE.sub(
        lambda m: f'{m.group("n")}={m.group("q")}{mask(m.group("v"))}{m.group("q")}',
        text,
    )

def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default

def preview(text: str, limit: int = MAX_SOURCE_PREVIEW) -> str:
    return redact(text[:limit])

def build_reader(apk: Path, analysis_path: Path, source_dir: Path | None, output: Path) -> dict[str, Any]:
    analysis = read_json(analysis_path, {})
    resources: list[dict[str, Any]] = []
    dex_strings: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []
    code_strings: list[dict[str, Any]] = []
    billing_evidence: dict[str, list[dict[str, Any]]] = {k:[] for k in BILLING_PATTERNS}

    def add_billing(kind: str, location: str, text: str):
        bucket=billing_evidence[kind]
        if len(bucket)>=600:return
        bucket.append({"location":location,"preview":redact(text[:1200])})

    if apk.exists() and zipfile.is_zipfile(apk):
        with zipfile.ZipFile(apk, "r") as z:
            for zi in z.infolist():
                p = zi.filename
                ext = Path(p).suffix.lower()
                if ext in TEXT_EXTS and zi.file_size and zi.file_size <= MAX_TEXT_ENTRY and len(resources) < MAX_RESOURCE_ITEMS:
                    try:
                        text = z.read(zi).decode("utf-8", "ignore")
                    except Exception:
                        text = ""
                    if text.strip():
                        resources.append({
                            "path": p,
                            "extension": ext or "[none]",
                            "bytes": zi.file_size,
                            "preview": preview(text, 18000),
                        })
                        for kind,pat in BILLING_PATTERNS.items():
                            for bm in pat.finditer(text[:MAX_TEXT_ENTRY]):
                                ln=text.count("\n",0,bm.start())+1
                                line=text.splitlines()[ln-1] if text.splitlines() and ln<=len(text.splitlines()) else bm.group(0)
                                add_billing(kind,f"{p}:{ln}",line)
                        if len(code_strings) < 5000:
                            for sm in STRING_LITERAL_RE.finditer(text[:MAX_TEXT_ENTRY]):
                                val=(sm.group(1) or sm.group(2) or "").strip()
                                if val:
                                    code_strings.append({"kind":"resource","location":p,"value":redact(val)[:500]})
                                    if len(code_strings) >= 5000: break
                if re.fullmatch(r"classes(?:\d+)?\.dex", Path(p).name):
                    try:
                        data = z.read(zi)
                    except Exception:
                        continue
                    count = 0
                    for m in PRINTABLE_RE.finditer(data):
                        s = m.group(0).decode("utf-8", "ignore")
                        if not s:
                            continue
                        red=redact(s[:900])
                        dex_strings.append({
                            "dex": p,
                            "offset": m.start(),
                            "value": red,
                        })
                        for kind,pat in BILLING_PATTERNS.items():
                            if pat.search(s): add_billing(kind,f"{p} @ {m.start()}",s)
                        if len(code_strings) < 5000:
                            code_strings.append({"kind":"dex","location":f"{p} @ {m.start()}","value":red[:500]})
                        count += 1
                        if count >= MAX_DEX_STRINGS_PER_DEX:
                            break

    if source_dir and source_dir.exists() and source_dir.is_dir():
        for p in source_dir.rglob("*"):
            if len(source_files) >= MAX_SOURCE_FILES:
                break
            if not p.is_file() or p.suffix.lower() not in SOURCE_EXTS:
                continue
            try:
                size = p.stat().st_size
                if size > MAX_SOURCE_BYTES:
                    source_files.append({
                        "path": str(p.relative_to(source_dir)),
                        "extension": p.suffix.lower(),
                        "bytes": size,
                        "preview": "",
                        "truncated": True,
                        "classes": [],
                        "methods": [],
                        "androidRefs": [],
                    })
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            classes = CLASS_RE.findall(text)[:80]
            methods = METHOD_RE.findall(text)[:160]
            refs = sorted(set(ANDROID_REF_RE.findall(text)))[:80]
            rel=str(p.relative_to(source_dir))
            source_files.append({
                "path": rel,
                "extension": p.suffix.lower(),
                "bytes": size,
                "lines": text.count("\n") + 1,
                "preview": preview(text),
                "truncated": len(text) > MAX_SOURCE_PREVIEW,
                "classes": classes,
                "methods": methods,
                "androidRefs": refs,
            })
            for kind,pat in BILLING_PATTERNS.items():
                for bm in pat.finditer(text[:MAX_SOURCE_BYTES]):
                    ln=text.count("\n",0,bm.start())+1
                    lines=text.splitlines()
                    line=lines[ln-1] if lines and ln<=len(lines) else bm.group(0)
                    add_billing(kind,f"{rel}:{ln}",line)
            if len(code_strings) < 5000:
                for sm in STRING_LITERAL_RE.finditer(text[:MAX_SOURCE_BYTES]):
                    val=(sm.group(1) or sm.group(2) or "").strip()
                    if val:
                        code_strings.append({"kind":"source","location":rel,"value":redact(val)[:500]})
                        if len(code_strings) >= 5000: break

    sections = {
        "manifest": analysis.get("manifest", {}),
        "permissions": analysis.get("permissions", {}),
        "components": analysis.get("components", {}),
        "urls": analysis.get("urls", {}),
        "api": analysis.get("api", {}),
        "keys": analysis.get("keys", {}),
        "certs": analysis.get("certs", {}),
        "native": analysis.get("native", {}),
        "webview": analysis.get("webview", {}),
        "crypto": analysis.get("crypto", {}),
        "risk": analysis.get("risk", {}),
        "files": analysis.get("files", {}),
    }

    url_items=(sections.get("urls") or {}).get("items",[]) if isinstance(sections.get("urls"),dict) else []
    api_items=(sections.get("api") or {}).get("items",[]) if isinstance(sections.get("api"),dict) else []
    web_items=(sections.get("webview") or {}).get("items",[]) if isinstance(sections.get("webview"),dict) else []
    crypto_items=(sections.get("crypto") or {}).get("items",[]) if isinstance(sections.get("crypto"),dict) else []
    component_items=(sections.get("components") or {}).get("items",[]) if isinstance(sections.get("components"),dict) else []
    risk_items=(sections.get("risk") or {}).get("items",[]) if isinstance(sections.get("risk"),dict) else []

    trace=[]
    nodes={}
    edges=[]
    def node(nid,kind,label):
        nodes[nid]={"id":nid,"kind":kind,"label":label}
    def edge(src,dst,relation,evidence=""):
        edges.append({"from":src,"to":dst,"relation":relation,"evidence":evidence})
        trace.append({"from":src,"relation":relation,"to":dst,"evidence":evidence})

    target_id="target"
    node(target_id,"target",(analysis.get("summary") or {}).get("package") or apk.name)
    for x in component_items[:1000]:
        name=str(x.get("name") or x)
        typ=str(x.get("type") or "component")
        cid="component:"+typ+":"+name
        node(cid,"component",f"{typ}: {name}")
        edge(target_id,cid,"declares",str(x.get("exported","")))

    host_counter=Counter()
    for x in url_items[:3000]:
        entry=str(x.get("entry") or "unknown")
        raw=str(x.get("url") or "")
        host=str(x.get("host") or "")
        sid="entry:"+entry
        node(sid,"entry",entry)
        uid="url:"+raw[:300]
        node(uid,"url",raw[:300])
        edge(sid,uid,"contains-url",host)
        if host:
            hid="host:"+host
            node(hid,"host",host)
            edge(uid,hid,"targets-host",host)
            host_counter[host]+=1

    for x in api_items[:3000]:
        entry=str(x.get("entry") or "unknown")
        val=str(x.get("preview") or "")
        sid="entry:"+entry
        aid="api:"+val[:260]
        node(sid,"entry",entry); node(aid,"api",val[:260])
        edge(sid,aid,"contains-api",val[:260])

    for x in web_items[:1500]:
        entry=str(x.get("entry") or "unknown")
        sid="entry:"+entry; wid="signal:webview"
        node(sid,"entry",entry); node(wid,"signal","WebView")
        edge(sid,wid,"webview-reference",str(x.get("preview") or "")[:300])

    for x in crypto_items[:1500]:
        entry=str(x.get("entry") or "unknown")
        sid="entry:"+entry; cid="signal:crypto"
        node(sid,"entry",entry); node(cid,"signal","Crypto")
        edge(sid,cid,"crypto-reference",str(x.get("preview") or "")[:300])

    routes=[]
    for x in component_items[:1000]:
        routes.append({"kind":"android-component","source":"AndroidManifest","type":x.get("type"),"name":x.get("name"),"exported":x.get("exported")})
    for x in url_items[:2000]:
        routes.append({"kind":"url","source":x.get("entry"),"destination":x.get("url"),"host":x.get("host"),"scheme":x.get("scheme")})
    for x in api_items[:2000]:
        routes.append({"kind":"api","source":x.get("entry"),"destination":x.get("preview")})

    ref_counter=Counter()
    ext_counter=Counter()
    package_counter=Counter()
    for x in source_files:
        ext_counter[x.get("extension") or "[none]"]+=1
        for ref in x.get("androidRefs",[]): ref_counter[ref]+=1
        parts=Path(x.get("path","")).parts
        if len(parts)>1: package_counter["/".join(parts[:min(4,len(parts)-1)])]+=1
    for x in resources: ext_counter[x.get("extension") or "[none]"]+=1
    severity_counter=Counter(str(x.get("severity") or "INFO") for x in risk_items)

    code_brains={
        "sourceFiles":len(source_files),
        "classes":sum(len(x.get("classes",[])) for x in source_files),
        "methods":sum(len(x.get("methods",[])) for x in source_files),
        "resources":len(resources),
        "dexStrings":len(dex_strings),
        "codeStrings":len(code_strings),
        "urls":len(url_items),
        "apis":len(api_items),
        "components":len(component_items),
        "webviewSignals":len(web_items),
        "cryptoSignals":len(crypto_items),
        "riskSignals":len(risk_items),
        "topAndroidRefs":ref_counter.most_common(25),
        "topExtensions":ext_counter.most_common(25),
        "topSourcePrefixes":package_counter.most_common(25),
        "topHosts":host_counter.most_common(25),
        "riskBySeverity":dict(severity_counter),
        "note":"Heuristic architecture summary only; it does not execute or emulate target code."
    }

    target_codes={
        "source":[{"path":x.get("path"),"extension":x.get("extension"),"classes":x.get("classes",[]),"methods":x.get("methods",[]),"androidRefs":x.get("androidRefs",[])} for x in source_files],
        "resources":[{"path":x.get("path"),"extension":x.get("extension"),"bytes":x.get("bytes")} for x in resources],
        "dexFiles":[x.get("path") for x in (sections.get("files") or {}).get("dex",[]) if isinstance(x,dict)],
        "native":sections.get("native",{}),
        "analysisSections":sorted(sections.keys())
    }


    maincode={
        "files":[{"path":x.get("path"),"classes":x.get("classes",[]),"methods":x.get("methods",[]),"androidRefs":x.get("androidRefs",[])} for x in source_files[:500]],
        "entryPoints":[x for x in component_items[:500]],
        "billingFiles":sorted({x.get("location","").split(":",1)[0] for group in billing_evidence.values() for x in group if x.get("location")})[:500],
        "note":"Static entry/code overview; no target code is executed."
    }
    urls_view={
        "items":url_items,
        "hosts":host_counter.most_common(200),
        "api":api_items[:2000]
    }
    billing_summary={k:{"count":len(v),"items":v} for k,v in billing_evidence.items()}
    verification={
        "hasPurchaseListener":bool(billing_evidence["callback"]),
        "hasPurchaseVerificationSignals":bool(billing_evidence["verify"]),
        "hasRecheckSignals":bool(billing_evidence["recheck"]),
        "hasFallbackSignals":bool(billing_evidence["fallback"]),
        "paymentSignals":len(billing_evidence["payment"]),
        "subscriptionSignals":len(billing_evidence["subscribes"]),
        "note":"Presence checks only. They do not prove billing correctness or successful server-side verification."
    }

    transparent={
        "nodes":list(nodes.values()),
        "edges":edges,
        "note":"Logical static relationship map. No target code is executed."
    }

    summary = {
        "apk": str(apk),
        "package": (analysis.get("summary") or {}).get("package", ""),
        "sha256": (analysis.get("summary") or {}).get("sha256", ""),
        "resourcePreviews": len(resources),
        "dexStrings": len(dex_strings),
        "sourceFiles": len(source_files),
        "sourceClasses": sum(len(x.get("classes", [])) for x in source_files),
        "sourceMethods": sum(len(x.get("methods", [])) for x in source_files),
        "jadxSourceAvailable": bool(source_dir and source_dir.exists()),
        "codeStrings": len(code_strings),
        "traceEdges": len(edges),
        "routes": len(routes),
        "paymentSignals": len(billing_evidence["payment"]),
        "subscriptionSignals": len(billing_evidence["subscribes"]),
        "callbackSignals": len(billing_evidence["callback"]),
        "fallbackSignals": len(billing_evidence["fallback"]),
        "verifySignals": len(billing_evidence["verify"]),
        "recheckSignals": len(billing_evidence["recheck"]),
        "redacted": True,
    }
    out = {
        "version": 1,
        "summary": summary,
        "sections": sections,
        "resources": resources,
        "dexStrings": dex_strings,
        "sourceFiles": source_files,
        "codeStrings": code_strings,
        "trace": trace,
        "routes": routes,
        "map": {"nodes":list(nodes.values()),"edges":edges},
        "transparent": transparent,
        "codeBrains": code_brains,
        "targetCodes": target_codes,
        "mainCode": maincode,
        "urlsView": urls_view,
        "billing": billing_summary,
        "verification": verification,
        "readerViews": [
            "main","code360","maincode","strings","codeview","transparent","trace","traces","routes","map","codebrains","targetcodes",
            "urls","verify","callback","fallback","recheck","subscribes","payment","etc",
            "overview","manifest","permissions","components","source","resources","dex",
            "urls","api","keys","certs","native","webview","crypto","risk","files"
        ],
        "note": "Source/resource/DEX previews are bounded and secret-like values are redacted.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out

def search_reader(data: dict[str, Any], query: str, limit: int = 200) -> list[dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return []
    results: list[dict[str, Any]] = []

    def add(kind: str, title: str, location: str, text: str):
        if len(results) >= limit:
            return
        hay = f"{title}\n{location}\n{text}".lower()
        if q in hay:
            results.append({
                "kind": kind,
                "title": title,
                "location": location,
                "preview": text[:1800],
            })

    for x in data.get("sourceFiles", []):
        add("source", x.get("path",""), x.get("extension",""), x.get("preview",""))
    for x in data.get("resources", []):
        add("resource", x.get("path",""), x.get("extension",""), x.get("preview",""))
    for x in data.get("dexStrings", []):
        add("dex", x.get("value","")[:120], f'{x.get("dex","")} @ {x.get("offset","")}', x.get("value",""))
    for x in data.get("codeStrings", []):
        add("string", x.get("value","")[:120], x.get("location",""), x.get("value",""))
    for x in data.get("trace", []):
        add("trace", str(x.get("relation","")), str(x.get("from",""))+" -> "+str(x.get("to","")), str(x.get("evidence","")))
    for x in data.get("routes", []):
        add("route", str(x.get("kind","route")), str(x.get("source","")), json.dumps(x,ensure_ascii=False))
    for kind,group in (data.get("billing") or {}).items():
        for x in group.get("items",[]) if isinstance(group,dict) else []:
            add(kind,kind,x.get("location",""),x.get("preview",""))

    for section_name in ("urls","api","keys","webview","crypto","risk","components","permissions","native","certs"):
        sec = (data.get("sections") or {}).get(section_name, {})
        items = sec.get("items", []) if isinstance(sec, dict) else []
        if isinstance(items, list):
            for idx, x in enumerate(items):
                add(section_name, section_name, str(idx), json.dumps(x, ensure_ascii=False))

    return results

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("apk")
    ap.add_argument("--analysis", default="apk-analysis.json")
    ap.add_argument("--source", default=".lola-apk/decompiled")
    ap.add_argument("--output", default="android-code-reader.json")
    args = ap.parse_args()

    apk = Path(args.apk).resolve()
    analysis = Path(args.analysis).resolve()
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    data = build_reader(apk, analysis, source if source.exists() else None, output)
    print(f"Android code reader written: {output}")
    print(json.dumps(data["summary"], indent=2))

if __name__ == "__main__":
    main()

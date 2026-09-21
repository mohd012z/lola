#!/usr/bin/env python3
import argparse, json
from collections import Counter, defaultdict
from pathlib import Path

PROTOCOL_SURFACES={"protocol","graphql","grpc","messaging-protocol","mail-protocol","remote-shell","dns","raw-socket","cleartext-http","tls"}
HIDDEN_SURFACES={"hidden-ui","hidden-config","sensitive-config"}
ANON_SURFACES={
    "privacy-ip-exposure","privacy-telemetry","privacy-persistent-id","privacy-fingerprinting",
    "privacy-network-exposure","privacy-advertising-id","privacy-cookie",
    "device-fingerprinting","device-identifiers","device-local-network","client-ip",
    "account-auth","personal-data"
}

CONTROL_GROUPS={
    "Secrets & credentials":{
        "surfaces":{"secrets","account-auth","sensitive-config"},
        "rules":["secret","private-key","provider-token","client-secret"],
        "review":"Remove secrets from client/source, rotate exposed credentials, and use a secret manager."
    },
    "Injection / execution":{
        "surfaces":{"security"},
        "rules":["xss","eval","command","sql","deserialization"],
        "review":"Validate and encode untrusted input; prefer parameterized/safe APIs and remove dynamic execution."
    },
    "Transport / TLS":{
        "surfaces":{"tls","cleartext-http","protocol"},
        "rules":["tls","http"],
        "review":"Use authenticated TLS, keep certificate verification enabled, and remove unintended cleartext transport."
    },
    "Authentication & session":{
        "surfaces":{"account-auth","device-biometric","privacy-cookie","privacy-persistent-id"},
        "rules":["cookie","token","auth","oauth"],
        "review":"Review session storage, cookie attributes, OAuth client type, redirect handling, and authentication boundaries."
    },
    "Filesystem & path":{
        "surfaces":{"filesystem","http-files","uploads","hidden-config","sensitive-config"},
        "rules":["path","file","upload"],
        "review":"Constrain resolved paths to approved roots and validate upload/download destinations."
    },
    "Network exposure":{
        "surfaces":{"listeners","client-ip","proxy-trust","network-addresses","private-network","raw-socket","dns"},
        "rules":["ssrf","proxy","bind","network"],
        "review":"Limit listener exposure, validate outbound destinations, and configure trusted proxy boundaries."
    },
    "Cryptography":{
        "surfaces":{"encryption","webcrypto","key-derivation","random","signatures","crypto-reference"},
        "rules":["cipher","hash","random","crypto"],
        "review":"Use current authenticated cryptography, unique nonces/IVs, secure randomness, and appropriate key management."
    },
    "Privacy & device":{
        "surfaces":ANON_SURFACES | {"device-media","device-location","device-permissions","device-files","device-notifications"},
        "rules":["device","privacy","fingerprint","telemetry","advertising"],
        "review":"Minimize identifying signals and permissions; collect only what the feature requires and disclose/consent appropriately."
    },
    "Browser messaging / CORS":{
        "surfaces":{"browser-navigation"},
        "rules":["postmessage","cors","redirect"],
        "review":"Pin origins, validate redirects, and avoid unnecessarily broad cross-origin access."
    },
}

def read_json(path, default):
    p=Path(path)
    if not p.exists(): return default
    try: return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception: return default

def normalize_result(r):
    extra=r.get("extra") or {}
    md=extra.get("metadata") or {}
    start=r.get("start") or {}
    end=r.get("end") or {}
    return {
        "rule":r.get("check_id") or "",
        "severity":str(extra.get("severity") or "INFO").upper(),
        "message":extra.get("message") or "",
        "path":r.get("path") or "",
        "line":start.get("line") or 0,
        "col":start.get("col") or 0,
        "endLine":end.get("line") or 0,
        "category":str(md.get("category") or "other"),
        "surface":str(md.get("surface") or md.get("category") or "other"),
        "confidence":str(md.get("confidence") or ""),
        "cwe":str(md.get("cwe") or ""),
        "lines":(extra.get("lines") or "").strip()
    }

def find_matches(findings, surfaces, rule_terms):
    out=[]
    for x in findings:
        rule=x["rule"].lower()
        if x["surface"] in surfaces or any(t in rule for t in rule_terms):
            out.append(x)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default="semgrep-results.json")
    ap.add_argument("--manifest",default="target-manifest.json")
    ap.add_argument("--urls",default="url-report.json")
    ap.add_argument("--output",default="scan-modes.json")
    args=ap.parse_args()

    raw=read_json(args.input,{"results":[]})
    manifest=read_json(args.manifest,{"files":[]})
    urls=read_json(args.urls,{"urls":[],"probeEnabled":False})
    findings=[normalize_result(r) for r in raw.get("results",[])]

    sev=Counter(x["severity"] for x in findings)
    cats=Counter(x["category"] for x in findings)
    surfaces=Counter(x["surface"] for x in findings)
    rules=Counter(x["rule"] for x in findings)
    files=Counter(x["path"] for x in findings if x["path"])

    hidden_files=[]
    for f in manifest.get("files",[]):
        path=str(f.get("path") or "")
        parts=path.replace("\\","/").split("/")
        dot=bool(f.get("isDotPath")) or any(p.startswith(".") and p not in {".",".."} for p in parts)
        hidden=bool(f.get("isHidden"))
        sensitive=(str(f.get("extension") or "").lower() in {".env",".key",".pem",".p12",".pfx",".jks",".keystore",".crt",".cer",".entitlements"} or
                   str(f.get("name") or "").lower() in {".env",".env.local",".env.production",".npmrc",".netrc","info.plist","androidmanifest.xml"})
        if dot or hidden or sensitive:
            hidden_files.append({**f,"reason":"; ".join([x for x in [
                "dot-path" if dot else "",
                "hidden-attribute" if hidden else "",
                "sensitive-config" if sensitive else ""
            ] if x])})

    protocol_findings=[x for x in findings if x["category"]=="protocol" or x["surface"] in PROTOCOL_SURFACES]
    protocol_counts=Counter(x["surface"] for x in protocol_findings)
    for u in urls.get("urls",[]):
        scheme=str(u.get("scheme") or "").lower()
        if scheme: protocol_counts[scheme]+=1

    hidden_findings=[x for x in findings if x["category"]=="hidden" or x["surface"] in HIDDEN_SURFACES]
    anonymous_findings=[x for x in findings if x["surface"] in ANON_SURFACES or x["category"] in {"privacy","account"}]
    anonymous_counts=Counter(x["surface"] for x in anonymous_findings)

    # Deep-dive: every detection with evidence and useful grouping.
    deep_dive={
        "summary":{
            "total":len(findings),
            "errors":sev.get("ERROR",0),
            "warnings":sev.get("WARNING",0),
            "info":sev.get("INFO",0),
            "rules":len(rules),
            "affectedFiles":len(files),
            "surfaces":len(surfaces)
        },
        "bySeverity":dict(sev),
        "bySurface":dict(surfaces),
        "byRule":rules.most_common(),
        "byFile":files.most_common(),
        "detections":findings
    }

    controls=[]
    for name,spec in CONTROL_GROUPS.items():
        matches=find_matches(findings,spec["surfaces"],spec["rules"])
        count=Counter(x["severity"] for x in matches)
        state="review" if matches else "no-detection"
        if count.get("ERROR",0)>0: state="priority-review"
        controls.append({
            "name":name,"state":state,"total":len(matches),
            "errors":count.get("ERROR",0),"warnings":count.get("WARNING",0),"info":count.get("INFO",0),
            "review":spec["review"],"findings":matches[:100]
        })

    securitycheck={
        "summary":{
            "controls":len(controls),
            "priorityReview":sum(1 for c in controls if c["state"]=="priority-review"),
            "review":sum(1 for c in controls if c["state"]=="review"),
            "noDetection":sum(1 for c in controls if c["state"]=="no-detection"),
            "errors":sev.get("ERROR",0),
            "warnings":sev.get("WARNING",0)
        },
        "controls":controls,
        "note":"No-detection means these custom rules did not flag the control area; it is not a security guarantee."
    }

    anon_urls=[]
    for u in urls.get("urls",[]):
        host=str(u.get("host") or "").lower()
        source=str(u.get("sourceUrl") or "").lower()
        if any(t in host or t in source for t in [
            "ipify","ipinfo","ifconfig","icanhazip","my-ip","ipapi","ip-api",
            "google-analytics","googletagmanager","mixpanel","segment","amplitude",
            "appsflyer","adjust","sentry","datadog","newrelic","matomo","plausible",
            "posthog","clarity","hotjar"
        ]):
            anon_urls.append(u)

    anonymous={
        "summary":{
            "exposureFindings":len(anonymous_findings),
            "publicIpOrTrackingUrls":len(anon_urls),
            "fingerprinting":anonymous_counts.get("privacy-fingerprinting",0)+anonymous_counts.get("device-fingerprinting",0),
            "telemetry":anonymous_counts.get("privacy-telemetry",0),
            "persistentIds":anonymous_counts.get("privacy-persistent-id",0)+anonymous_counts.get("device-identifiers",0),
            "networkExposure":anonymous_counts.get("privacy-network-exposure",0)+anonymous_counts.get("client-ip",0)+anonymous_counts.get("device-local-network",0),
            "accountLinkage":anonymous_counts.get("account-auth",0)
        },
        "counts":dict(anonymous_counts),
        "findings":anonymous_findings,
        "urls":anon_urls,
        "note":"This mode audits identity/privacy exposure. It does not attempt to conceal identity, bypass tracking controls, or evade platform/security systems."
    }

    stepview={
        "before":{"title":"Before","items":[
            {"label":"Target selected","value":manifest.get("target","")},
            {"label":"Candidate files discovered","value":manifest.get("fileCount",len(manifest.get("files",[])))},
            {"label":"Hidden/sensitive paths identified","value":len(hidden_files)},
            {"label":"Static URLs inventoried","value":urls.get("urlCount",len(urls.get("urls",[])))}
        ]},
        "during":{"title":"During","items":[
            {"label":"Semgrep findings produced","value":len(findings)},
            {"label":"Errors","value":sev.get("ERROR",0)},
            {"label":"Warnings","value":sev.get("WARNING",0)},
            {"label":"Info/inventory","value":sev.get("INFO",0)},
            {"label":"Protocol surfaces","value":sum(protocol_counts.values())},
            {"label":"Privacy/anonymity exposures","value":len(anonymous_findings)},
            {"label":"Live public URL verification","value":"enabled" if urls.get("probeEnabled") else "static-only"}
        ]},
        "after":{"title":"After","items":[
            {"label":"Affected files","value":len(files)},
            {"label":"Categories","value":len(cats)},
            {"label":"Surfaces","value":len(surfaces)},
            {"label":"Security control groups requiring review","value":sum(1 for c in controls if c["state"]!="no-detection")},
            {"label":"Outputs","value":"manifest + URL map + Semgrep JSON + modes JSON + visual HTML"}
        ]}
    }

    out={
        "stepview":stepview,
        "protocol":{"counts":dict(protocol_counts),"findings":protocol_findings,"urls":[u for u in urls.get("urls",[]) if u.get("scheme")]},
        "hidden":{"files":hidden_files,"findings":hidden_findings,"counts":{
            "files":len(hidden_files),"findings":len(hidden_findings),
            "dotPaths":sum(1 for x in hidden_files if "dot-path" in x.get("reason","")),
            "hiddenAttribute":sum(1 for x in hidden_files if "hidden-attribute" in x.get("reason","")),
            "sensitiveConfig":sum(1 for x in hidden_files if "sensitive-config" in x.get("reason",""))
        }},
        "deep-dive":deep_dive,
        "securitycheck":securitycheck,
        "anonymous":anonymous,
        "360":{"summary":{
            "files":manifest.get("fileCount",len(manifest.get("files",[]))),
            "urls":urls.get("urlCount",len(urls.get("urls",[]))),
            "findings":len(findings),"errors":sev.get("ERROR",0),"warnings":sev.get("WARNING",0),"info":sev.get("INFO",0),
            "protocolSurfaces":sum(protocol_counts.values()),"hiddenFiles":len(hidden_files),
            "privacyExposures":len(anonymous_findings),"controlGroupsReview":sum(1 for c in controls if c["state"]!="no-detection"),
            "categories":dict(cats),"surfaces":dict(surfaces)
        }}
    }
    Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Scan modes written: {Path(args.output).resolve()}")

if __name__=="__main__":
    main()

#!/usr/bin/env python3
import argparse, json
from collections import Counter, defaultdict
from pathlib import Path

PROTOCOL_SURFACES={"protocol","graphql","grpc","messaging-protocol","mail-protocol","remote-shell","dns","raw-socket","cleartext-http","tls"}
HIDDEN_SURFACES={"hidden-ui","hidden-config","sensitive-config"}

def read_json(path, default):
    p=Path(path)
    if not p.exists(): return default
    try: return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception: return default

def normalize_result(r):
    extra=r.get("extra") or {}
    md=extra.get("metadata") or {}
    return {
        "rule":r.get("check_id") or "",
        "severity":str(extra.get("severity") or "INFO").upper(),
        "message":extra.get("message") or "",
        "path":r.get("path") or "",
        "line":(r.get("start") or {}).get("line") or 0,
        "category":str(md.get("category") or "other"),
        "surface":str(md.get("surface") or md.get("category") or "other")
    }

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
        if scheme:
            protocol_counts[scheme]+=1

    hidden_findings=[x for x in findings if x["category"]=="hidden" or x["surface"] in HIDDEN_SURFACES]

    stepview={
        "before":{
            "title":"Before",
            "items":[
                {"label":"Target selected","value":manifest.get("target","")},
                {"label":"Candidate files discovered","value":manifest.get("fileCount",len(manifest.get("files",[])))},
                {"label":"Hidden/sensitive paths identified","value":len(hidden_files)},
                {"label":"Static URLs inventoried","value":urls.get("urlCount",len(urls.get("urls",[])))}
            ]
        },
        "during":{
            "title":"During",
            "items":[
                {"label":"Semgrep findings produced","value":len(findings)},
                {"label":"Errors","value":sev.get("ERROR",0)},
                {"label":"Warnings","value":sev.get("WARNING",0)},
                {"label":"Info/inventory","value":sev.get("INFO",0)},
                {"label":"Protocol surfaces","value":sum(protocol_counts.values())},
                {"label":"Live public URL verification","value":"enabled" if urls.get("probeEnabled") else "static-only"}
            ]
        },
        "after":{
            "title":"After",
            "items":[
                {"label":"Affected files","value":len({x["path"] for x in findings if x["path"]})},
                {"label":"Categories","value":len(cats)},
                {"label":"Surfaces","value":len(surfaces)},
                {"label":"Outputs","value":"manifest + URL map + Semgrep JSON + modes JSON + visual HTML"}
            ]
        }
    }

    out={
        "stepview":stepview,
        "protocol":{
            "counts":dict(protocol_counts),
            "findings":protocol_findings,
            "urls":[u for u in urls.get("urls",[]) if u.get("scheme")]
        },
        "hidden":{
            "files":hidden_files,
            "findings":hidden_findings,
            "counts":{
                "files":len(hidden_files),
                "findings":len(hidden_findings),
                "dotPaths":sum(1 for x in hidden_files if "dot-path" in x.get("reason","")),
                "hiddenAttribute":sum(1 for x in hidden_files if "hidden-attribute" in x.get("reason","")),
                "sensitiveConfig":sum(1 for x in hidden_files if "sensitive-config" in x.get("reason",""))
            }
        },
        "360":{
            "summary":{
                "files":manifest.get("fileCount",len(manifest.get("files",[]))),
                "urls":urls.get("urlCount",len(urls.get("urls",[]))),
                "findings":len(findings),
                "errors":sev.get("ERROR",0),
                "warnings":sev.get("WARNING",0),
                "info":sev.get("INFO",0),
                "protocolSurfaces":sum(protocol_counts.values()),
                "hiddenFiles":len(hidden_files),
                "categories":dict(cats),
                "surfaces":dict(surfaces)
            }
        }
    }
    Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Scan modes written: {Path(args.output).resolve()}")

if __name__=="__main__":
    main()

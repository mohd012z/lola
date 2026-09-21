#!/usr/bin/env python3
"""Persistent target library and built-in Lola command/function catalog."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LIB_ROOT = ROOT / ".lola-library"
TARGET_DIR = LIB_ROOT / "targets"
INDEX_FILE = LIB_ROOT / "library.json"

COMMANDS = [
    {"id":"/library","group":"System","label":"Built-in Library","purpose":"Search every Lola command/function, tool requirement and output","platform":["Android","Windows","Linux"],"cost":"low","tools":[],"outputs":[".lola-library/library.json"]},
    {"id":"/targetlibrary","group":"System","label":"Target Library","purpose":"Saved target identities, SHA-256, scan plans, history and output links","platform":["Android","Windows","Linux"],"cost":"low","tools":[],"outputs":[".lola-library/targets/*.json"]},
    {"id":"/targetplan","group":"System","label":"Target Plan","purpose":"Choose what Lola should inspect before starting a scan","platform":["Android","Windows","Linux"],"cost":"low","tools":[],"outputs":["target lastPlan"]},
    # APK
    {"id":"/apk360","group":"APK","label":"APK 360","purpose":"Complete APK overview","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["apk-analysis.json","apk-report.html"]},
    {"id":"/apkmanifest","group":"APK","label":"Manifest","purpose":"Package, SDK and AndroidManifest review","platform":["Android","Windows","Linux"],"cost":"low","tools":["apkanalyzer|apktool|aapt"],"outputs":["apk-analysis.json"]},
    {"id":"/apkpermissions","group":"APK","label":"Permissions","purpose":"Declared and sensitive Android permissions","platform":["Android","Windows","Linux"],"cost":"low","tools":["manifest decoder recommended"],"outputs":["apk-analysis.json"]},
    {"id":"/apkcomponents","group":"APK","label":"Components","purpose":"Activities, services, receivers, providers and exported state","platform":["Android","Windows","Linux"],"cost":"low","tools":["manifest decoder recommended"],"outputs":["apk-analysis.json"]},
    {"id":"/apkurls","group":"APK","label":"URLs","purpose":"Recover literal URLs from DEX/resources/assets","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["apk-analysis.json"]},
    {"id":"/apkapi","group":"APK","label":"API","purpose":"API/auth/media/GraphQL endpoint references","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["apk-analysis.json"]},
    {"id":"/apkkeys","group":"APK","label":"Keys","purpose":"Redacted password/token/key references","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["apk-analysis.json"],"redaction":True},
    {"id":"/apkcerts","group":"APK","label":"Certificates","purpose":"Signing/certificate evidence","platform":["Android","Windows","Linux"],"cost":"low","tools":["apksigner|keytool recommended"],"outputs":["apk-analysis.json"]},
    {"id":"/apknative","group":"APK","label":"Native .SO","purpose":"ABI and native library inventory","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":["apk-analysis.json"]},
    {"id":"/apkwebview","group":"APK","label":"WebView","purpose":"WebView and JavaScript bridge references","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["apk-analysis.json"]},
    {"id":"/apkcrypto","group":"APK","label":"Crypto","purpose":"Cipher/hash/KDF/key-store references","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["apk-analysis.json"]},
    {"id":"/apkfiles","group":"APK","label":"Files","purpose":"Full APK ZIP/file inventory","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":["apk-analysis.json"]},
    {"id":"/apkcode","group":"APK","label":"Code / JADX","purpose":"Optional JADX decompilation status/source","platform":["Android","Windows","Linux"],"cost":"high","tools":["jadx"],"outputs":[".lola-apk/decompiled"]},
    {"id":"/apkrisk","group":"APK","label":"Risk Review","purpose":"Consolidated static review findings","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":["apk-analysis.json"]},
    {"id":"/apktools","group":"APK","label":"Tools","purpose":"Show locally available APK analysis tools","platform":["Android","Windows","Linux"],"cost":"low","tools":[],"outputs":[]},

    # Security
    {"id":"/360","group":"Security","label":"360 Overview","purpose":"Whole source/security surface","platform":["Windows","Linux"],"cost":"medium","tools":["semgrep","python"],"outputs":["semgrep-report.html"]},
    {"id":"/deep-dive","group":"Security","label":"Deep Dive","purpose":"Every security detection and evidence row","platform":["Windows","Linux"],"cost":"medium","tools":["semgrep","python"],"outputs":["semgrep-results.json","semgrep-report.html"]},
    {"id":"/securitycheck","group":"Security","label":"Security Check","purpose":"Security-control review by domain","platform":["Windows","Linux"],"cost":"medium","tools":["semgrep"],"outputs":["scan-modes.json"]},
    {"id":"/anonymus","group":"Security","label":"Privacy / Anonymous","purpose":"Privacy and identity exposure inventory","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["scan-modes.json","preflight-analysis.json"]},
    {"id":"/stepview","group":"Security","label":"Step View","purpose":"Before/during/after scan flow","platform":["Windows","Linux"],"cost":"low","tools":[],"outputs":["scan-modes.json"]},
    {"id":"/protocol","group":"Security","label":"Protocol","purpose":"Protocol and transport inventory","platform":["Windows","Linux"],"cost":"medium","tools":["semgrep"],"outputs":["scan-modes.json"]},
    {"id":"/hidden","group":"Security","label":"Hidden","purpose":"Hidden files/config/UI surfaces","platform":["Windows","Linux"],"cost":"medium","tools":["semgrep"],"outputs":["scan-modes.json"]},

    # Code
    {"id":"/deep-code","group":"Code","label":"Deep Code","purpose":"Combined source analysis","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/extraction","group":"Code","label":"Extraction","purpose":"Imports, functions, classes, routes","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codesummary","group":"Code","label":"Code Summary","purpose":"Repository/source summary","platform":["Windows","Linux"],"cost":"low","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codeview","group":"Code","label":"Code View","purpose":"Redacted source browser","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codepassword","group":"Code","label":"Password / Key","purpose":"Redacted secret-reference locations","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"],"redaction":True},
    {"id":"/codestring","group":"Code","label":"Strings","purpose":"Static string inventory","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codetransparent","group":"Code","label":"Transparent Flow","purpose":"Heuristic source/sink map","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codemodification","group":"Code","label":"Modification","purpose":"File/storage/DB/UI/network write points","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codefallback","group":"Code","label":"Fallback","purpose":"Retry/default/error/fallback paths","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codeurls","group":"Code","label":"Code URLs","purpose":"URLs linked to source locations","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codeencryption","group":"Code","label":"Encryption","purpose":"Crypto/password/key usage","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/hiddenmode","group":"Code","label":"Hidden Mode","purpose":"Hidden code/UI/config evidence","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},

    # Network
    {"id":"/deep-network","group":"Network","label":"Deep Network","purpose":"Combined network analysis","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["network-analysis.json"]},
    {"id":"/trace","group":"Network","label":"Trace","purpose":"URL/DNS/redirect/TLS application trace","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["network-analysis.json"]},
    {"id":"/route","group":"Network","label":"Route","purpose":"Application route map","platform":["Windows","Linux"],"cost":"low","tools":["python"],"outputs":["network-analysis.json"]},
    {"id":"/map","group":"Network","label":"Map","purpose":"Logical source→host→IP graph","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":["network-analysis.json","preflight-analysis.json"]},
    {"id":"/visible","group":"Network","label":"Visible","purpose":"Publicly visible source/resolution surface","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["network-analysis.json"]},
    {"id":"/realip","group":"Network","label":"Real IP","purpose":"Resolved public IP and discovery references","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":["network-analysis.json"]},
    {"id":"/cctv","group":"Network","label":"CCTV Monitor","purpose":"Live scan-process monitor; no camera recording","platform":["Windows","Linux"],"cost":"low","tools":["python"],"outputs":["network-monitor.html"]},
    {"id":"/normal","group":"Network","label":"Normal","purpose":"Compact network view","platform":["Windows","Linux"],"cost":"low","tools":["python"],"outputs":["network-analysis.json"]},

    # Preflight
    {"id":"/preflight","group":"Pre-scan","label":"Preflight","purpose":"Before-Semgrep target analysis","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/viewextraction","group":"Pre-scan","label":"View Extraction","purpose":"Functions/classes/config/routes before Semgrep","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/viewurls","group":"Pre-scan","label":"View URLs","purpose":"Pre-scan URL inventory","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/routes","group":"Pre-scan","label":"Routes","purpose":"Pre-scan application routes","platform":["Windows","Linux"],"cost":"low","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/api","group":"Pre-scan","label":"API","purpose":"Pre-scan API references","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/keys","group":"Pre-scan","label":"Keys","purpose":"Redacted key/password/token references","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"],"redaction":True},
    {"id":"/hiddentraces","group":"Pre-scan","label":"Hidden Traces","purpose":"Detect hidden/stealth-like code references","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/hidemodes","group":"Pre-scan","label":"Hide Modes","purpose":"Detect hidden/private/silent modes","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/hidelog","group":"Pre-scan","label":"Hide Log Detection","purpose":"Detect log-suppression/clearing code","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/ipmirror","group":"Pre-scan","label":"IP Mirror","purpose":"Mirror app destination DNS/IP resolution","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/certs","group":"Pre-scan","label":"Certs","purpose":"Certificate inventory/public cert copies","platform":["Windows","Linux"],"cost":"low","tools":["python"],"outputs":["preflight-analysis.json"]},
]

APK_PLAN = [
    {"id":"identity","label":"Target identity","description":"Filename, size, SHA-256, ZIP/APK validity","default":True,"cost":"low"},
    {"id":"manifest","label":"Manifest + SDK","description":"Package, min/target SDK and application flags","default":True,"cost":"low"},
    {"id":"permissions","label":"Permissions","description":"Declared and sensitive Android permissions","default":True,"cost":"low"},
    {"id":"components","label":"Components","description":"Activities/services/receivers/providers/exported state","default":True,"cost":"low"},
    {"id":"urls","label":"URLs","description":"Literal URLs in DEX/resources/assets","default":True,"cost":"medium"},
    {"id":"api","label":"API references","description":"API/auth/media/GraphQL-style paths","default":True,"cost":"medium"},
    {"id":"keys","label":"Keys / tokens","description":"Secret-like references with mandatory redaction","default":True,"cost":"medium"},
    {"id":"certs","label":"Certificates","description":"Signing entries and signer metadata when tools exist","default":True,"cost":"low"},
    {"id":"native","label":"Native libraries","description":"ABI and .so inventory","default":True,"cost":"low"},
    {"id":"webview","label":"WebView","description":"WebView/JavaScript bridge references","default":True,"cost":"medium"},
    {"id":"crypto","label":"Crypto","description":"Cipher/hash/KDF/key-store references","default":True,"cost":"medium"},
    {"id":"files","label":"File inventory","description":"APK ZIP entries, sizes and CRCs","default":True,"cost":"low"},
    {"id":"risk","label":"Risk review","description":"Static review signals and summary","default":True,"cost":"low"},
    {"id":"decompile","label":"JADX decompile","description":"Resource-heavy optional source extraction","default":False,"cost":"high"},
    {"id":"store_target","label":"Store target in Library","description":"Save identity, plan, history and output links","default":True,"cost":"low"},
]

def _now() -> int:
    return int(time.time())

def _ensure():
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(json.dumps({"version":1,"targets":[]},indent=2),encoding="utf-8")

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def catalog() -> dict[str, Any]:
    return {"commands":COMMANDS,"apkPlan":APK_PLAN}

def target_id_from_sha(sha256: str) -> str:
    return sha256[:24]

def target_path(target_id: str) -> Path:
    return TARGET_DIR / f"{target_id}.json"

def load_target(target_id: str) -> dict[str, Any] | None:
    _ensure()
    p=target_path(target_id)
    if not p.exists(): return None
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return None

def save_target(record: dict[str, Any]) -> dict[str, Any]:
    _ensure()
    tid=record["id"]
    target_path(tid).write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding="utf-8")
    idx=json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    refs=[x for x in idx.get("targets",[]) if x.get("id")!=tid]
    refs.append({
        "id":tid,"sha256":record.get("sha256"),"name":record.get("name"),
        "size":record.get("size"),"firstSeen":record.get("firstSeen"),
        "lastSeen":record.get("lastSeen"),"lastStatus":record.get("lastStatus"),
        "package":record.get("apk",{}).get("package",""),"riskFindings":record.get("apk",{}).get("riskFindings",0),
        "scanCount":len(record.get("scans",[]))
    })
    refs.sort(key=lambda x:x.get("lastSeen",0),reverse=True)
    idx["targets"]=refs
    INDEX_FILE.write_text(json.dumps(idx,indent=2,ensure_ascii=False),encoding="utf-8")
    return record

def register_target(path: Path, original_name: str | None=None) -> dict[str, Any]:
    _ensure()
    sha=sha256_file(path)
    tid=target_id_from_sha(sha)
    existing=load_target(tid) or {}
    now=_now()
    rec={
        **existing,
        "id":tid,
        "sha256":sha,
        "name":original_name or path.name,
        "storedPath":str(path),
        "size":path.stat().st_size,
        "firstSeen":existing.get("firstSeen",now),
        "lastSeen":now,
        "lastStatus":existing.get("lastStatus","uploaded"),
        "lastPlan":existing.get("lastPlan",[]),
        "apk":existing.get("apk",{}),
        "outputs":existing.get("outputs",{}),
        "scans":existing.get("scans",[]),
        "notes":existing.get("notes",""),
    }
    return save_target(rec)

def set_plan(target_id: str, checks: list[str], mode: str, options: dict[str,Any]) -> dict[str,Any] | None:
    rec=load_target(target_id)
    if not rec:return None
    rec["lastPlan"]=checks
    rec["lastMode"]=mode
    rec["lastOptions"]=options
    rec["lastSeen"]=_now()
    return save_target(rec)

def complete_scan(target_id: str, status: str, mode: str, checks: list[str], analysis: dict[str,Any] | None, outputs: dict[str,str], started: float|None=None, finished: float|None=None) -> dict[str,Any] | None:
    rec=load_target(target_id)
    if not rec:return None
    if analysis:
        s=analysis.get("summary",{})
        rec["apk"]={
            "package":s.get("package",""),"minSdk":s.get("minSdk",""),"targetSdk":s.get("targetSdk",""),
            "permissions":s.get("permissions",0),"exportedComponents":s.get("exportedComponents",0),
            "urls":s.get("urls",0),"nativeLibraries":s.get("nativeLibraries",0),
            "riskFindings":s.get("riskFindings",0),"abis":s.get("abis",{})
        }
    rec["outputs"]={**rec.get("outputs",{}),**outputs}
    rec["lastStatus"]=status
    rec["lastSeen"]=_now()
    rec["lastPlan"]=checks
    rec["scans"].append({
        "time":_now(),"status":status,"mode":mode,"checks":checks,
        "started":started,"finished":finished,"outputs":outputs
    })
    rec["scans"]=rec["scans"][-100:]
    return save_target(rec)

def list_targets() -> list[dict[str,Any]]:
    _ensure()
    try:return json.loads(INDEX_FILE.read_text(encoding="utf-8")).get("targets",[])
    except Exception:return []

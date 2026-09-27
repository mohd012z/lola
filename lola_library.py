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
    {"id":"/targetlibrary","group":"System","label":"Target Library","purpose":"Saved target identities, SHA-256, scan plans, history and output links","platform":["Android","Windows","Linux"],"cost":"low","tools":[],"outputs":[".lola-library/targets/<target-id>/target.json"]},
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
    {"id":"/androidreader","group":"Android Reader","label":"Android Code Reader","purpose":"Browse manifest, DEX strings, resources, decompiled source, URLs/APIs, WebView, crypto, native libraries and findings from one target library","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/readersearch","group":"Android Reader","label":"Reader Search","purpose":"Search the built-in Android code reader across redacted source/resource/DEX evidence","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/readersource","group":"Android Reader","label":"Reader Source","purpose":"Browse retained JADX source previews by file and extension","platform":["Android","Windows","Linux"],"cost":"high","tools":["jadx recommended"],"outputs":["android-code-reader.json",".lola-apk/decompiled"]},
    {"id":"/readerresources","group":"Android Reader","label":"Reader Resources","purpose":"Browse text resources/assets extracted from the APK container","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/readerdex","group":"Android Reader","label":"Reader DEX Strings","purpose":"Search redacted printable strings recovered from classes*.dex","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/deep-dive main","group":"Android Reader","label":"Deep-Dive Main","purpose":"Master target view combining identity, manifest, permissions, components, code, strings, URLs/APIs, flow map, findings and storage","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/code360","group":"Android Reader","label":"Code 360","purpose":"Combined code/resource/DEX architecture overview for the selected APK target","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/coderemove","group":"Android Reader","label":"Remove Generated Code","purpose":"Delete Lola-generated reader/JADX artifacts for the selected target only; original APK and external logs are not touched","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":[]},
    {"id":"/codebrains","group":"Android Reader","label":"Code Brains","purpose":"Heuristic architecture summary: classes, methods, Android APIs, WebView/network/crypto signals, extensions and hosts","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/targetcodes","group":"Android Reader","label":"Target Codes","purpose":"Target-specific code index grouped by source, resource, DEX, native and analysis evidence","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/test apk realtime","group":"Android Runtime","label":"Test APK Realtime","purpose":"Read-only runtime observation for an authorized installed/running package via ADB/logcat","platform":["Android","Windows","Linux"],"cost":"medium","tools":["adb"],"outputs":["runtime-analysis.json","runtime-events.jsonl"]},
    {"id":"/traces","group":"Android Runtime","label":"Runtime Traces","purpose":"Show categorized read-only runtime log evidence for the selected test package","platform":["Android","Windows","Linux"],"cost":"medium","tools":["adb"],"outputs":["runtime-analysis.json"]},
    {"id":"/maincode","group":"Android Reader","label":"Main Code","purpose":"Show source entry points, Android components and files containing billing/runtime-relevant code","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python","jadx recommended"],"outputs":["android-code-reader.json"]},
    {"id":"/urls","group":"Android Reader","label":"URLs","purpose":"Show target URLs, hosts and API references from APK/static evidence","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/verify","group":"Android Reader","label":"Verify","purpose":"Review purchase-state, acknowledgement, backend/server and verification signals; does not bypass billing","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/callback","group":"Android Reader","label":"Callbacks","purpose":"Review purchase/billing/listener callback references such as PurchasesUpdatedListener and billing setup callbacks","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/fallback","group":"Android Reader","label":"Fallback","purpose":"Review retry/reconnect/error/fallback handling paths","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/recheck","group":"Android Reader","label":"Recheck","purpose":"Review query/restore/resume/recheck signals such as queryPurchasesAsync and reconnect handling","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/subscribes","group":"Android Reader","label":"Subscriptions","purpose":"Review subscription/base-plan/offer/renewal/entitlement integration references without modifying subscription state","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/payment","group":"Android Reader","label":"Payment","purpose":"Review Google Play Billing/payment integration references without automating or bypassing purchases","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/etc","group":"Android Reader","label":"Etc","purpose":"Combined miscellaneous target evidence: tools, risk, native, certs, files and unmatched reader sections","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":["android-code-reader.json"]},
    {"id":"/frida-library","group":"Frida","label":"Frida Library","purpose":"Internal Lola catalog of safe Frida modes, related tools and observation-only probes","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":["frida-analysis.json","frida-events.jsonl"]},
    {"id":"/frida-runtime","group":"Frida","label":"Frida Runtime","purpose":"Attach-only observation of an authorized running Android app","platform":["Android","Windows","Linux"],"cost":"medium","tools":["frida Python bindings"],"outputs":["frida-analysis.json","frida-events.jsonl"]},
    {"id":"/frida-root","group":"Frida","label":"Frida Root Server","purpose":"Optional rooted-device backend using an already-running frida-server; Lola does not root the device or start/hide the server","platform":["Android","Windows","Linux"],"cost":"medium","tools":["frida","frida-server"],"outputs":["frida-analysis.json","frida-events.jsonl"]},
    {"id":"/frida-gadget","group":"Frida","label":"Frida Gadget","purpose":"Non-root backend for Gadget already embedded in an app/test build you own or are authorized to instrument","platform":["Android","Windows","Linux"],"cost":"medium","tools":["frida","Frida Gadget","adb optional"],"outputs":["frida-analysis.json","frida-events.jsonl"]},
    {"id":"/frida-probes","group":"Frida","label":"Frida Probes","purpose":"Safe probes for app classes/method names, lifecycle, URLs, DNS, intents, storage metadata, crypto metadata, billing signals, callbacks and timers","platform":["Android","Windows","Linux"],"cost":"medium","tools":["frida"],"outputs":["frida-analysis.json"]},
    {"id":"/toolchain","group":"Toolchain","label":"Built-in Toolchain","purpose":"Status/install/remove Lola-managed analysis toolchains without committing third-party binaries to Git","platform":["Android","Windows","Linux","macOS"],"cost":"low","tools":["python"],"outputs":[".lola-tools/installed.json"]},
    {"id":"/apktool","group":"Toolchain","label":"Apktool 3.0.3","purpose":"Checksum-verified managed Apktool for manifest/resource/smali decoding","platform":["Android","Windows","Linux","macOS"],"cost":"medium","tools":["java"],"outputs":[".lola-tools/apktool"]},
    {"id":"/gradle","group":"Toolchain","label":"Gradle 9.7.1","purpose":"Pinned managed Gradle distribution for Java/Android build workflows","platform":["Android","Windows","Linux","macOS"],"cost":"high","tools":["java"],"outputs":[".lola-tools/gradle"]},
    {"id":"/ghidra","group":"Toolchain","label":"Ghidra 12.1.3","purpose":"Pinned checksum-verified desktop/native-binary analysis tool; requires JDK 25","platform":["Windows","Linux","macOS"],"cost":"very-high","tools":["java 25"],"outputs":[".lola-tools/ghidra"]},
    {"id":"/hermes","group":"Toolchain","label":"Hermes / hermesc","purpose":"Detect the target React Native project's matching Hermes compiler/runtime; no blind cross-version install","platform":["Android","Windows","Linux","macOS"],"cost":"low","tools":["project toolchain"],"outputs":[]},
    {"id":"/toolstatus","group":"Toolchain","label":"Tool Status","purpose":"Show managed/system/project-detected tool availability, path, version and Java compatibility","platform":["Android","Windows","Linux","macOS"],"cost":"low","tools":["python"],"outputs":[]},
    {"id":"/handoff","group":"System","label":"Handoff Adapter","purpose":"Validate or run a versioned local MyAI/MSA One handoff contract without uploading source or collecting secrets","platform":["Windows","Linux","macOS"],"cost":"low","tools":["python"],"outputs":["*.result.json"]},

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
    {"id":"/codeview","group":"Code","label":"Code View","purpose":"Redacted source browser; on Android uses the built-in APK/JADX Code Reader","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python","jadx recommended"],"outputs":["code-analysis.json","android-code-reader.json"]},
    {"id":"/codepassword","group":"Code","label":"Password / Key","purpose":"Redacted secret-reference locations","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"],"redaction":True},
    {"id":"/codestring","group":"Code","label":"Strings","purpose":"Static/redacted string inventory; on Android combines DEX, resource and source strings","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json","android-code-reader.json"]},
    {"id":"/codetransparent","group":"Code","label":"Transparent Flow","purpose":"Heuristic static relationship map; on Android links APK entries to URLs/APIs/WebView/crypto signals","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json","android-code-reader.json"]},
    {"id":"/codemodification","group":"Code","label":"Modification","purpose":"File/storage/DB/UI/network write points","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codefallback","group":"Code","label":"Fallback","purpose":"Retry/default/error/fallback paths","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codeurls","group":"Code","label":"Code URLs","purpose":"URLs linked to source locations","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/codeencryption","group":"Code","label":"Encryption","purpose":"Crypto/password/key usage","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},
    {"id":"/hiddenmode","group":"Code","label":"Hidden Mode","purpose":"Hidden code/UI/config evidence","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["code-analysis.json"]},

    # Network
    {"id":"/deep-network","group":"Network","label":"Deep Network","purpose":"Combined network analysis","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["network-analysis.json"]},
    {"id":"/trace","group":"Network","label":"Trace","purpose":"Application trace; on Android traces APK entry/source to URL/API/host evidence","platform":["Android","Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["network-analysis.json","android-code-reader.json"]},
    {"id":"/route","group":"Network","label":"Route","purpose":"Application route map","platform":["Windows","Linux"],"cost":"low","tools":["python"],"outputs":["network-analysis.json"]},
    {"id":"/map","group":"Network","label":"Map","purpose":"Logical static graph; on Android links target/components/entries/URLs/APIs/hosts","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":["network-analysis.json","preflight-analysis.json","android-code-reader.json"]},
    {"id":"/visible","group":"Network","label":"Visible","purpose":"Publicly visible source/resolution surface","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["network-analysis.json"]},
    {"id":"/realip","group":"Network","label":"Real IP","purpose":"Resolved public IP and discovery references","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":["network-analysis.json"]},
    {"id":"/cctv","group":"Network","label":"CCTV Monitor","purpose":"Live scan-process monitor; no camera recording","platform":["Windows","Linux"],"cost":"low","tools":["python"],"outputs":["network-monitor.html"]},
    {"id":"/normal","group":"Network","label":"Normal","purpose":"Compact network view","platform":["Windows","Linux"],"cost":"low","tools":["python"],"outputs":["network-analysis.json"]},

    # Preflight
    {"id":"/preflight","group":"Pre-scan","label":"Preflight","purpose":"Before-Semgrep target analysis","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/viewextraction","group":"Pre-scan","label":"View Extraction","purpose":"Functions/classes/config/routes before Semgrep","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/viewurls","group":"Pre-scan","label":"View URLs","purpose":"Pre-scan URL inventory","platform":["Windows","Linux"],"cost":"medium","tools":["python"],"outputs":["preflight-analysis.json"]},
    {"id":"/routes","group":"Pre-scan","label":"Routes","purpose":"Application routes; on Android combines manifest components and URL/API destinations","platform":["Android","Windows","Linux"],"cost":"low","tools":["python"],"outputs":["preflight-analysis.json","android-code-reader.json"]},
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
    {"id":"android_reader","label":"Build Android Code Reader","description":"Create searchable manifest/DEX/resource/source/library index","default":True,"cost":"medium"},
    {"id":"store_target","label":"Keep APK in Target Library","description":"Retain one library copy of the APK by SHA-256 target ID","default":False,"cost":"storage"},
    {"id":"store_analysis","label":"Store analysis detail","description":"Save target-specific apk-analysis.json in the target library","default":True,"cost":"low"},
    {"id":"store_report","label":"Store visual report","description":"Save target-specific apk-report.html in the target library","default":True,"cost":"low"},
    {"id":"store_decompiled","label":"Store JADX source in Library","description":"Retain decompiled source under the target library when JADX runs","default":False,"cost":"high-storage"},
]

FUNCTIONS = [
    {"id":"register_target","group":"Library Function","label":"Register Target","purpose":"Compute SHA-256 target ID and create/update persistent target metadata","module":"lola_library.py","outputs":["target.json"]},
    {"id":"set_plan","group":"Library Function","label":"Save Target Plan","purpose":"Persist selected pre-scan checks, report mode and options","module":"lola_library.py","outputs":["target.json"]},
    {"id":"complete_scan","group":"Library Function","label":"Complete Scan","purpose":"Append scan history and summarize APK results","module":"lola_library.py","outputs":["target.json"]},
    {"id":"archive_artifacts","group":"Library Function","label":"Archive Artifacts","purpose":"Copy selected APK/analysis/report/reader/decompiled artifacts into the target folder","module":"lola_library.py","outputs":["target artifact folder"]},
    {"id":"remove_generated_code","group":"Library Function","label":"Remove Generated Code","purpose":"Delete Lola-generated reader/JADX artifacts for one target without deleting the original APK, analysis/report history or external logs","module":"lola_library.py","outputs":[]},
    {"id":"analyze-apk.py","group":"Analyzer Function","label":"APK Analyzer","purpose":"Perform selected APK package/static-analysis checks with secret redaction","module":"analyze-apk.py","outputs":["apk-analysis.json"]},
    {"id":"build-apk-report.py","group":"Report Function","label":"APK Report Builder","purpose":"Create interactive APK HTML report","module":"build-apk-report.py","outputs":["apk-report.html"]},
    {"id":"android_code_reader.py","group":"Reader Function","label":"Android Code Reader Indexer","purpose":"Build searchable redacted Android code/resource/DEX library","module":"android_code_reader.py","outputs":["android-code-reader.json"]},
    {"id":"lola_mobile.py","group":"UI Function","label":"Lola Mobile Server","purpose":"Android localhost UI, upload, target plan, live scan, library and reader APIs","module":"lola_mobile.py","outputs":["localhost UI"]},
    {"id":"apk_runtime_monitor.py","group":"Runtime Function","label":"APK Runtime Observer","purpose":"Read-only ADB/logcat observer for an authorized installed/running package; no billing state changes or network interception","module":"apk_runtime_monitor.py","outputs":["runtime-analysis.json","runtime-events.jsonl"]},
    {"id":"frida_library.py","group":"Frida Function","label":"Frida Probe Library","purpose":"Built-in safe Frida modes, related-tool catalog and observation-only Java probes","module":"frida_library.py","outputs":[]},
    {"id":"frida_runtime.py","group":"Frida Function","label":"Frida Runtime Runner","purpose":"Attach-only authorized Frida runner supporting root/frida-server and non-root Gadget backends","module":"frida_runtime.py","outputs":["frida-analysis.json","frida-events.jsonl"]},
    {"id":"lola_toolchain.py","group":"Toolchain Function","label":"Managed Toolchain","purpose":"Download/checksum/cache/status/remove pinned Apktool, Gradle and Ghidra and detect Hermes/JADX/Android SDK tools","module":"lola_toolchain.py","outputs":[".lola-tools/installed.json"]}
]

STORAGE = {
    "root": ".lola-library",
    "index": ".lola-library/library.json",
    "targetPattern": ".lola-library/targets/<target-id>/target.json",
    "targetApk": ".lola-library/targets/<target-id>/target.apk",
    "analysis": ".lola-library/targets/<target-id>/apk-analysis.json",
    "report": ".lola-library/targets/<target-id>/apk-report.html",
    "reader": ".lola-library/targets/<target-id>/android-code-reader.json",
    "decompiled": ".lola-library/targets/<target-id>/decompiled/",
    "runtimeAnalysis": ".lola-library/targets/<target-id>/runtime-analysis.json",
    "runtimeEvents": ".lola-library/targets/<target-id>/runtime-events.jsonl",
    "fridaAnalysis": ".lola-library/targets/<target-id>/frida-analysis.json",
    "fridaEvents": ".lola-library/targets/<target-id>/frida-events.jsonl",
    "temporaryUpload": ".lola-mobile/uploads/",
    "targetId": "first 24 hex characters of the APK SHA-256"
}

def _now() -> int:
    return int(time.time())

def _ensure():
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    data={"version":2,"commands":COMMANDS,"functions":FUNCTIONS,"apkPlan":APK_PLAN,"storage":STORAGE,"targets":[]}
    if INDEX_FILE.exists():
        try:
            old=json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            data["targets"]=old.get("targets",[])
        except Exception:
            pass
    INDEX_FILE.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def catalog() -> dict[str, Any]:
    _ensure()
    return {"commands":COMMANDS,"functions":FUNCTIONS,"apkPlan":APK_PLAN,"storage":STORAGE}

def target_id_from_sha(sha256: str) -> str:
    return sha256[:24]

def target_folder(target_id: str) -> Path:
    return TARGET_DIR / target_id

def target_path(target_id: str) -> Path:
    return target_folder(target_id) / "target.json"

def legacy_target_path(target_id: str) -> Path:
    return TARGET_DIR / f"{target_id}.json"

def artifact_paths(target_id: str) -> dict[str, str]:
    folder=target_folder(target_id)
    return {
        "folder":str(folder),
        "record":str(folder/"target.json"),
        "apk":str(folder/"target.apk"),
        "analysis":str(folder/"apk-analysis.json"),
        "report":str(folder/"apk-report.html"),
        "reader":str(folder/"android-code-reader.json"),
        "decompiled":str(folder/"decompiled"),
        "runtimeAnalysis":str(folder/"runtime-analysis.json"),
        "runtimeEvents":str(folder/"runtime-events.jsonl"),
        "fridaAnalysis":str(folder/"frida-analysis.json"),
        "fridaEvents":str(folder/"frida-events.jsonl"),
    }

def load_target(target_id: str) -> dict[str, Any] | None:
    _ensure()
    p=target_path(target_id)
    legacy=legacy_target_path(target_id)
    if not p.exists() and legacy.exists():
        p=legacy
    if not p.exists(): return None
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return None

def save_target(record: dict[str, Any]) -> dict[str, Any]:
    _ensure()
    tid=record["id"]
    folder=target_folder(tid)
    folder.mkdir(parents=True,exist_ok=True)
    record["storage"]=artifact_paths(tid)
    target_path(tid).write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding="utf-8")
    legacy=legacy_target_path(tid)
    if legacy.exists():
        try: legacy.unlink()
        except Exception: pass
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

def archive_artifacts(
    target_id: str,
    source_apk: Path | None=None,
    analysis: Path | None=None,
    report: Path | None=None,
    reader: Path | None=None,
    decompiled: Path | None=None,
    keep_apk: bool=False,
    keep_analysis: bool=True,
    keep_report: bool=True,
    keep_reader: bool=True,
    keep_decompiled: bool=False,
) -> dict[str,str]:
    import shutil
    rec=load_target(target_id)
    if not rec:return {}
    folder=target_folder(target_id)
    folder.mkdir(parents=True,exist_ok=True)
    stored={}
    def copy_file(src: Path | None, dst: Path, enabled: bool):
        if not enabled or not src or not src.exists() or not src.is_file(): return
        shutil.copy2(src,dst)
        stored[dst.name]=str(dst)
    copy_file(source_apk, folder/"target.apk", keep_apk)
    copy_file(analysis, folder/"apk-analysis.json", keep_analysis)
    copy_file(report, folder/"apk-report.html", keep_report)
    copy_file(reader, folder/"android-code-reader.json", keep_reader)
    if keep_decompiled and decompiled and decompiled.exists() and decompiled.is_dir():
        dst=folder/"decompiled"
        if dst.exists(): shutil.rmtree(dst,ignore_errors=True)
        shutil.copytree(decompiled,dst)
        stored["decompiled"]=str(dst)
    rec["outputs"]={**rec.get("outputs",{}),**stored}
    rec["lastSeen"]=_now()
    save_target(rec)
    return stored

def remove_generated_code(target_id: str) -> dict[str,Any]:
    import shutil
    rec=load_target(target_id)
    if not rec:return {"removed":[],"missing":True}
    removed=[]
    paths=artifact_paths(target_id)
    reader=Path(paths["reader"])
    decompiled=Path(paths["decompiled"])
    if reader.exists() and reader.is_file():
        reader.unlink()
        removed.append(str(reader))
    if decompiled.exists() and decompiled.is_dir():
        shutil.rmtree(decompiled,ignore_errors=True)
        removed.append(str(decompiled))
    outputs=rec.get("outputs",{})
    for k in ["android-code-reader.json","reader","decompiled"]:
        outputs.pop(k,None)
    rec["outputs"]=outputs
    rec["lastSeen"]=_now()
    save_target(rec)
    return {"removed":removed,"targetId":target_id}

def list_targets() -> list[dict[str,Any]]:
    _ensure()
    try:return json.loads(INDEX_FILE.read_text(encoding="utf-8")).get("targets",[])
    except Exception:return []

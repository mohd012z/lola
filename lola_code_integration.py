"""Integrated code-workbench planner for Lola.

Combines extraction, compilation planning, conversion, packaging, hashing and
user-owned data encryption/decryption into one auditable task graph. Protected
third-party binaries are never decrypted or bypassed.
"""
from __future__ import annotations
import hashlib, json, shutil
from pathlib import Path
from lola_universal_converter import detect, plan as conversion_plan, available_tools

SOURCE={
 ".py":"python",".js":"javascript",".ts":"typescript",".tsx":"typescript",
 ".java":"java",".kt":"kotlin",".c":"c",".cpp":"cpp",".cc":"cpp",".cs":"csharp",
 ".sh":"shell",".ps1":"powershell",".mq4":"mql4",".mq5":"mql5",".smali":"smali"
}
COMPILE={
 "python":["python -m py_compile"],
 "javascript":["node --check"],"typescript":["tsc --noEmit"],
 "java":["javac"],"kotlin":["kotlinc"],"c":["cc"],"cpp":["c++"],
 "csharp":["dotnet build"],"shell":["bash -n"],"powershell":["pwsh parser"],
 "mql4":["MetaEditor compile"],"mql5":["MetaEditor compile"],"smali":["smali assemble"]
}

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def identify(path):
    p=Path(path);info=detect(p);lang=SOURCE.get(p.suffix.lower())
    return {"path":str(p),"name":p.name,"extension":p.suffix.lower(),"language":lang,
            "format":info,"sha256":sha256(p)}

def compile_plan(path):
    item=identify(path);lang=item["language"]
    return {"supported":lang in COMPILE,"language":lang,"routes":COMPILE.get(lang,[]),
            "note":"Plan only; use the language's installed compiler in a controlled workspace."}

def extraction_plan(path):
    p=Path(path);ext=p.suffix.lower()
    if ext in (".zip",".apk",".aab",".jar"):route=["bounded archive inventory","safe workspace extraction","recursive evidence"]
    elif ext in SOURCE:route=["syntax/static source inspection","symbols/imports/calls","specialist checks"]
    elif ext in (".exe",".dll",".so",".elf"):route=["header/section inventory","strings/signatures","optional static native analysis"]
    else:route=["fingerprint","strings/signatures","bounded chunks","evidence export"]
    return {"route":route,"read_only":True,"target_execution":False}

def crypto_plan(path,operation):
    op=(operation or "").lower()
    if op not in ("encrypt","decrypt"):return {"supported":False,"reason":"operation must be encrypt or decrypt"}
    return {"supported":True,"operation":op,"scope":"user-owned data/workspace artifacts only",
            "recommended":"authenticated encryption (AES-GCM or ChaCha20-Poly1305) with a user-supplied key/password KDF",
            "guardrails":["never guess passwords","never bypass DRM/protection","never decrypt protected third-party code without authorization"]}

def merge_plan(paths):
    items=[identify(p) for p in paths]
    langs=sorted({x["language"] for x in items if x["language"]})
    return {"inputs":items,"languages":langs,"strategy":[
        "inventory public interfaces and data contracts",
        "detect duplicate symbols and dependency conflicts",
        "create adapters instead of concatenating incompatible languages",
        "preserve provenance for every merged component",
        "compile/test each component before integration",
        "run final cross-function verification"]}

def idea(path):
    i=identify(path);lang=i["language"] or i["format"]["kind"]
    return {"target":i,"ideas":[
        "separate parser/extractor from presentation",
        "add explicit input/output schemas",
        "add bounded processing and structured warnings",
        "add specialist syntax/compile checks",
        "record provenance and verification status"],
        "rule":"suggest architecture changes; do not fabricate recovered source or hidden semantics"}

def wrap_script(path):
    i=identify(path);lang=i["language"]
    return {"target":i,"wrapper":{"input":"explicit file/workspace path","steps":[
        "identify","inspect","extract evidence","specialist check","optional conversion","verify"],
        "output":"JSON report + explicit artifacts"},
        "compile":compile_plan(path),"tools":available_tools()}

def task(command,target,arg=None):
    cmd=(command or "").lower().lstrip("/");p=Path(target)
    if cmd in ("codeintelligent","codeidea","codescriptidea"):return idea(p)
    if cmd in ("codewrap","codescript"):return wrap_script(p)
    if cmd in ("codecompile","compilecode"):return compile_plan(p)
    if cmd in ("codeextract","extractcode"):return extraction_plan(p)
    if cmd in ("codeconvert","convertcode"):return conversion_plan(p,arg or "evidence360")
    if cmd in ("codeencrypt","codedecrypt"):return crypto_plan(p,"encrypt" if "encrypt" in cmd else "decrypt")
    return {"error":"unsupported integration command","command":command}

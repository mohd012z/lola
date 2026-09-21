#!/usr/bin/env python3
"""Python capability workbench for Lola.

Static-first inspection for Python/Linux/host/path/link/URL/header/layer/encoding
and optional tool capability reporting. It never imports or executes inspected
Python targets. Ghidra is static only; Frida is reported as authorized attach-only.
"""
from __future__ import annotations
import ast, base64, codecs, hashlib, json, os, platform, re, shutil, sys
from pathlib import Path
from lola_python_path_doctor import analyze as path_analyze
from lola_toolchain import status as tool_status

MAX_TEXT=4*1024*1024
URL_RX=re.compile(r'https?://[^\s\'"<>]+',re.I)

def host():
    return {"python":sys.version.split()[0],"executable":sys.executable,"implementation":platform.python_implementation(),
            "os":platform.system(),"release":platform.release(),"machine":platform.machine(),
            "linux":platform.system().lower()=="linux","cwd":str(Path.cwd()),"path_entries":sys.path[:32]}

def _read(p):
    p=Path(p)
    if p.stat().st_size>MAX_TEXT:raise ValueError("Python text target exceeds 4 MiB inspection limit")
    return p.read_text(encoding="utf-8-sig",errors="replace")

def header(p):
    s=_read(p);lines=s.splitlines()
    return {"file":str(p),"shebang":lines[0] if lines and lines[0].startswith("#!") else None,
            "encoding_cookie":next((x for x in lines[:2] if "coding" in x),None),
            "future_imports":[x for x in lines[:80] if x.strip().startswith("from __future__ import")],
            "docstring":ast.get_docstring(ast.parse(s))}

def urls(p):
    s=_read(p);return {"file":str(p),"urls":sorted(set(URL_RX.findall(s)))[:256]}

def links(root):
    r=path_analyze(root);return {"local_import_edges":r["local_import_edges"],
        "external_or_unresolved":r["external_or_unresolved"],"entry_points":r["entry_points"]}

def layers(root):
    r=path_analyze(root);groups={"entry":[],"dispatch":[],"analysis":[],"conversion":[],"tooling":[],"other":[]}
    for f in r["files"]:
        n=f["file"].lower()
        k="entry" if f["entry_points"] else "dispatch" if "dispatch" in n else "conversion" if "convert" in n else "tooling" if "tool" in n else "analysis" if any(x in n for x in ("inspect","doctor","extract","analy")) else "other"
        groups[k].append(f["file"])
    return groups

def pylist(root):
    r=path_analyze(root);return [{"file":x["file"],"functions":len(x["functions"]),"classes":len(x["classes"]),
                                  "imports":len(x["imports"]),"processes":len(x["processes"])} for x in r["files"]]

def trace(root):
    r=path_analyze(root);return {"entry_points":r["entry_points"],"process_launches":r["process_launches"],
                                  "local_import_edges":r["local_import_edges"],"syntax_faults":r["syntax_faults"]}

def codec(p,mode,arg=None):
    raw=Path(p).read_bytes()
    if mode=="decode":
        text=raw.decode("utf-8",errors="replace").strip()
        try:b=base64.b64decode(text,validate=True);return {"ok":True,"codec":"base64","size":len(b),"sha256":hashlib.sha256(b).hexdigest(),"text":b.decode("utf-8","replace")[:MAX_TEXT]}
        except Exception:return {"ok":False,"error":"input is not strict Base64 text"}
    enc=(arg or "base64").lower()
    if enc!="base64":return {"ok":False,"error":"only explicit Base64 encoding is enabled"}
    return {"ok":True,"codec":"base64","text":base64.b64encode(raw).decode("ascii"),"source_sha256":hashlib.sha256(raw).hexdigest()}

def converter(p,arg=None):
    p=Path(p);target=(arg or "ast-json").lower();s=_read(p);tree=ast.parse(s)
    if target in ("ast","ast-json"):return {"ok":True,"representation":"ast-json","tree":ast.dump(tree,indent=2)}
    if target=="normalized-source":return {"ok":True,"representation":"normalized-source","text":ast.unparse(tree)}
    return {"ok":False,"error":"supported targets: ast-json, normalized-source"}

def inverter(p):
    s=_read(p);tree=ast.parse(s)
    return {"ok":True,"note":"Structural reverse view only; not bytecode decompilation or original-source recovery.",
            "ast":ast.dump(tree,indent=2),"normalized_source":ast.unparse(tree)}

def tools(project=None):
    st=tool_status(Path(project) if project else None)
    wanted={"ghidra","frida"}
    return {"host":host(),"tools":[x for x in st["tools"] if x["id"] in wanted],
            "policy":{"ghidra":"static native analysis only","frida":"authorized attach-only runtime evidence; no stealth/patching"}}

def capability(root="."):
    return {"schema":"Lola-PythonCapability-1","host":host(),"paths":path_analyze(root),
            "features":["python","linux/host","converter","structural inverter","header","trace","link/import graph","URL inventory",
                        "Base64 decoder/encoder","layer map","file list","Ghidra capability","Frida capability","nano editor detection",
                        "update/upgrade planning"],
            "nano":shutil.which("nano"),"tooling":tools(root)}

def update_plan(upgrade=False):
    return {"mode":"upgrade" if upgrade else "update","automatic":False,
            "steps":["run Code Doctor and Python path report","review dependency/tool status","update only explicit managed components",
                     "re-run syntax/import checks","retain rollback commit"],
            "note":"No package, OS, Python, Ghidra or Frida update is performed without an explicit managed update action."}

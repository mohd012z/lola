"""Recursive read-only deep extraction for Lola.

Carves recognizable embedded objects and recursively analyzes safe archive members.
All output is provenance-linked; targets are never executed and encrypted/protected
content is not bypassed.
"""
from __future__ import annotations
import hashlib, json, shutil, tempfile, zipfile
from pathlib import Path
from lola_extractor_core import extract

MAGICS=((b"PK\x03\x04","zip"),(b"\x1f\x8b\x08","gzip"),(b"\x7fELF","elf"),
        (b"MZ","pe"),(b"%PDF","pdf"),(b"SQLite format 3\x00","sqlite"))
MAX_DEPTH=3
MAX_CHILDREN=512
MAX_TOTAL=512*1024*1024

def carve(data:bytes):
    out=[]
    for sig,kind in MAGICS:
        start=0
        while len(out)<MAX_CHILDREN:
            off=data.find(sig,start)
            if off<0:break
            out.append({"offset":off,"kind":kind,"signature":sig.hex()})
            start=off+1
    return sorted(out,key=lambda x:x["offset"])

def _safe_member(root:Path,name:str):
    dst=(root/name).resolve()
    return dst if (dst==root or root in dst.parents) else None

def _zip_children(path:Path,workspace:Path):
    children=[];total=0
    if not zipfile.is_zipfile(path):return children
    with zipfile.ZipFile(path) as z:
        for info in z.infolist()[:MAX_CHILDREN]:
            if info.is_dir():continue
            total+=info.file_size
            if total>MAX_TOTAL:break
            dst=_safe_member(workspace,info.filename)
            if dst is None:continue
            dst.parent.mkdir(parents=True,exist_ok=True)
            try:
                with z.open(info) as src,open(dst,"wb") as f:
                    shutil.copyfileobj(src,f,1024*1024)
            except RuntimeError: # encrypted member or unsupported method
                children.append({"name":info.filename,"status":"not-extracted","reason":"encrypted-or-unsupported"})
                continue
            children.append({"name":info.filename,"path":str(dst),"size":info.file_size,"status":"extracted"})
    return children

def deep_extract(path,workspace=None,depth=0,seen=None):
    p=Path(path)
    if seen is None:seen=set()
    report=extract(p)
    sha=report["sha256"]
    node={"file":p.name,"sha256":sha,"depth":depth,"evidence":report,
          "carved":carve(p.read_bytes()),"children":[]}
    if sha in seen:
        node["deduplicated"]=True;return node
    seen.add(sha)
    if depth>=MAX_DEPTH:return node
    if report["kind"]=="ZIP/APK" or zipfile.is_zipfile(p):
        root=Path(workspace or tempfile.mkdtemp(prefix="lola-deep-"))/("d"+str(depth)+"-"+sha[:12])
        root.mkdir(parents=True,exist_ok=True)
        for child in _zip_children(p,root):
            if child.get("status")=="extracted":
                try:child["analysis"]=deep_extract(child["path"],root,depth+1,seen)
                except Exception as exc:child["analysis_error"]=type(exc).__name__+": "+str(exc)
            node["children"].append(child)
    return node

def graph(node):
    edges=[]
    def walk(n,parent=None):
        nid=n.get("sha256","")[:16]
        if parent:edges.append({"from":parent,"to":nid,"relation":"contains"})
        for c in n.get("children",[]):
            a=c.get("analysis")
            if a:walk(a,nid)
    walk(node)
    return edges

def save_deep(node,out_dir):
    d=Path(out_dir);d.mkdir(parents=True,exist_ok=True)
    payload={"schema":"Lola-DeepEvidence360-1","root":node,"graph":graph(node),
             "limits":{"depth":MAX_DEPTH,"children":MAX_CHILDREN,"bytes":MAX_TOTAL},
             "policy":{"target_executed":False,"password_guessing":False,"protection_bypass":False}}
    (d/"deep-evidence360.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    return d/"deep-evidence360.json"

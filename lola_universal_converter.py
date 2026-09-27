"""Lola universal conversion planner.

Converts compatible representations using explicit adapters.  "Any format" means
auto-detect and choose a valid conversion path; it never pretends arbitrary binary
formats are losslessly interchangeable.
"""
from __future__ import annotations
import ast, json, shutil
from pathlib import Path

TEXT_EXT={".txt",".md",".log",".csv",".json",".xml",".svg",".css",".html",".htm",
          ".py",".js",".mjs",".cjs",".ts",".java",".c",".h",".cpp",".cc",".cxx",".hpp",".cs",".vb",".vbs",".wsf",
          ".sh",".ps1",".mq4",".mq5",".smali"}
SOURCE_EXT={".py":"python",".js":"javascript",".mjs":"javascript",".cjs":"javascript",".ts":"typescript",".java":"java",
            ".c":"c",".h":"cpp-header",".cpp":"cpp",".cc":"cpp",".cxx":"cpp",".hpp":"cpp-header",".cs":"csharp",
            ".vb":"visual-basic",".vbs":"vbscript",".wsf":"vbscript",".sh":"shell",".ps1":"powershell",
            ".mq4":"mql4",".mq5":"mql5",".smali":"smali"}

def detect(path):
    p=Path(path);head=p.read_bytes()[:16];ext=p.suffix.lower()
    if head[:4]==b"dex\n":kind="dex"
    elif head[:4]==b"\xca\xfe\xba\xbe":kind="java-class"
    elif head[:4]==b"\x00asm":kind="wasm"
    elif head[:4]==b"\x7fELF":kind="elf"
    elif head[:2]==b"MZ":kind="pe"
    elif head[:4]==b"PK\x03\x04":kind="zip-container"
    elif head==b"SQLite format 3\x00":kind="sqlite"
    elif ext in SOURCE_EXT:kind=SOURCE_EXT[ext]
    elif ext in TEXT_EXT:kind="text"
    else:kind="binary"
    return {"kind":kind,"extension":ext,"size":p.stat().st_size}

def python_summary(path):
    p=Path(path);src=p.read_text(encoding="utf-8",errors="replace")
    try:tree=ast.parse(src)
    except SyntaxError as e:return {"valid":False,"error":str(e)}
    funcs=[];classes=[];imports=[]
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):funcs.append({"name":n.name,"line":n.lineno})
        elif isinstance(n,ast.ClassDef):classes.append({"name":n.name,"line":n.lineno})
        elif isinstance(n,ast.Import):imports.extend(a.name for a in n.names)
        elif isinstance(n,ast.ImportFrom):imports.append(n.module or "")
    return {"valid":True,"language":"python","functions":funcs[:10000],"classes":classes[:5000],"imports":imports[:10000]}

def text_to_json(path,out):
    p=Path(path);dst=Path(out);dst.parent.mkdir(parents=True,exist_ok=True)
    payload={"source":p.name,"text":p.read_text(encoding="utf-8",errors="replace")}
    dst.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    return {"ok":True,"output":str(dst),"representation":"text-envelope"}

def copy_text(path,out,encoding="utf-8"):
    p=Path(path);dst=Path(out);dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(p.read_text(encoding=encoding,errors="replace"),encoding="utf-8")
    return {"ok":True,"output":str(dst),"encoding":"utf-8"}

def available_tools():
    return {x:shutil.which(x) for x in ("python","python3","java","javac","jadx","baksmali","smali","ffmpeg","pandoc")}

def plan(path,target_format):
    info=detect(path);dst=target_format.lower().lstrip(".")
    src=info["kind"]
    if src=="dex" and dst=="smali":route=["baksmali"]
    elif src=="dex" and dst=="java":route=["jadx"]
    elif src=="smali" and dst=="dex":route=["smali"]
    elif src=="smali" and dst=="java":route=["smali","temporary-dex","jadx"]
    elif src=="python" and dst in ("json","ast"):route=["python-ast"]
    elif Path(path).suffix.lower() in TEXT_EXT and dst in ("txt","json"):route=["text-normalizer"]
    else:route=["evidence360-export"]
    return {"source":info,"target":dst,"route":route,
            "lossless":route in (["text-normalizer"],),
            "note":"Unsupported semantic conversions fall back to evidence export rather than fabricated source."}

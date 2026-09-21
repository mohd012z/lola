"""Lola integration brain for extraction, conversion and code-composition planning.

Builds evidence-backed workflows. It does not invent source equivalence: merge/combine
operations produce plans unless the inputs are ordinary text/source files.
"""
from __future__ import annotations
import ast, hashlib, json
from pathlib import Path
from lola_universal_converter import detect, plan as conversion_plan
from lola_extractor_core import extract

SOURCE={".py",".js",".ts",".tsx",".java",".kt",".c",".h",".cpp",".hpp",".cs",".vb",".vbs",".sh",".ps1",".mq4",".mq5",".smali",".html",".css",".xml",".json",".md",".txt"}

def fingerprint(path):
    p=Path(path);h=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return {"path":str(p),"name":p.name,"extension":p.suffix.lower(),"size":p.stat().st_size,"sha256":h.hexdigest(),"format":detect(p)}

def idea(path):
    p=Path(path);info=fingerprint(p);ext=p.suffix.lower()
    routes=[{"task":"extract","engine":"evidence360","reason":"preserve observable provenance"}]
    if ext in SOURCE:routes.append({"task":"inspect","engine":"code-doctor","reason":"source/static structure"})
    if ext==".pdf":routes += [{"task":"ocr-readiness","engine":"pdf-ocr"},{"task":"convert","engine":"office/html"}]
    elif ext in (".doc",".docx",".xls",".xlsx",".ods",".odt",".rtf",".csv"):
        routes.append({"task":"convert","engine":"office-engine"})
    elif ext in (".apk",".aab",".dex",".smali"):
        routes.append({"task":"inspect","engine":"android-converter"})
    else:routes.append({"task":"convert-plan","engine":"universal-converter"})
    return {"source":info,"routes":routes,"policy":{"execute_target":False,"fabricate_source":False}}

def combine(paths):
    items=[fingerprint(x) for x in paths]
    exts={x["extension"] for x in items}
    textual=all(x["extension"] in SOURCE for x in items)
    return {"inputs":items,"compatible_text_merge":textual,
            "strategy":"sectioned-source-bundle" if textual else "evidence-bundle",
            "warning":None if textual else "Binary/compiled inputs are combined as evidence references, not fabricated source."}

def wrap(path,target=None):
    p=Path(path);result={"source":fingerprint(p),"idea":idea(p)}
    if target:result["conversion"]=conversion_plan(p,target)
    return result

def script_idea(path):
    p=Path(path);ext=p.suffix.lower();base=idea(p)
    if ext==".py":
        try:
            tree=ast.parse(p.read_text(encoding="utf-8",errors="replace"))
            base["symbols"]=[n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))][:5000]
        except SyntaxError as e:base["syntax_error"]={"line":e.lineno,"message":str(e)}
    base["suggested_pipeline"]=[x["task"] for x in base["routes"]]
    return base

def intelligent(path,target=None):
    p=Path(path)
    return {"brain":"Lola-IntegrationBrain-1","workflow":wrap(p,target),
            "evidence":extract(p,include_numbers=False),
            "decision":"Use detected format and explicit adapters; unsupported semantic conversions stay evidence-only."}

#!/usr/bin/env python3
"""Lola Python path/process deep inspector.

Maps Python files, imports, entry points and subprocess launches without executing
the inspected repository code. Produces JSON suitable for Code Doctor/fallback bots.
"""
from __future__ import annotations
import argparse, ast, json, sys
from pathlib import Path

SKIP={".git",".lola-tools","node_modules","build","dist","__pycache__",".gradle",".idea"}
MAX_FILE=4*1024*1024

def pyfiles(root):
    root=Path(root).resolve()
    for p in sorted(root.rglob("*.py")):
        if p.is_file() and not any(x in SKIP for x in p.parts) and p.stat().st_size<=MAX_FILE:
            yield p

def _name(n):
    if isinstance(n,ast.Name):return n.id
    if isinstance(n,ast.Attribute):
        a=_name(n.value);return (a+"." if a else "")+n.attr
    return None

def inspect_file(path,root):
    rel=str(path.relative_to(root));row={"file":rel,"imports":[],"functions":[],"classes":[],"processes":[],"entry_points":[],"path_usage":[],"issues":[]}
    try:s=path.read_text(encoding="utf-8-sig",errors="replace");tree=ast.parse(s,filename=rel)
    except SyntaxError as e:
        row["issues"].append({"type":"syntax","line":e.lineno,"message":str(e)});return row
    for n in ast.walk(tree):
        if isinstance(n,ast.Import):
            row["imports"] += [x.name for x in n.names]
        elif isinstance(n,ast.ImportFrom):
            row["imports"].append(("."*n.level)+(n.module or ""))
        elif isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            row["functions"].append({"name":n.name,"line":n.lineno})
        elif isinstance(n,ast.ClassDef):
            row["classes"].append({"name":n.name,"line":n.lineno})
        elif isinstance(n,ast.Call):
            fn=_name(n.func) or ""
            if fn in ("subprocess.run","subprocess.call","subprocess.Popen","subprocess.check_call","subprocess.check_output","os.system"):
                row["processes"].append({"call":fn,"line":n.lineno})
            if fn.startswith("Path") or fn in ("open","os.path.join","os.path.abspath","os.path.realpath"):
                row["path_usage"].append({"call":fn,"line":n.lineno})
        elif isinstance(n,ast.If):
            try:test=ast.unparse(n.test)
            except Exception:test=""
            if "__name__" in test and "__main__" in test:
                row["entry_points"].append({"line":n.lineno,"kind":"__main__"})
    return row

def analyze(root="."):
    root=Path(root).resolve();rows=[inspect_file(p,root) for p in pyfiles(root)]
    modules={Path(r["file"]).stem:r["file"] for r in rows};edges=[];missing=[]
    std=getattr(sys,"stdlib_module_names",set())
    for r in rows:
        for imp in r["imports"]:
            top=imp.lstrip(".").split(".")[0] if imp else ""
            if not top:continue
            if top in modules:edges.append({"from":r["file"],"to":modules[top],"import":imp,"kind":"local"})
            elif top not in std:missing.append({"from":r["file"],"import":imp,"kind":"external-or-unresolved"})
    processes=[dict(x,file=r["file"]) for r in rows for x in r["processes"]]
    entries=[dict(x,file=r["file"]) for r in rows for x in r["entry_points"]]
    syntax=[{"file":r["file"],"issues":r["issues"]} for r in rows if r["issues"]]
    return {"schema":"Lola-PythonPath-1","root":str(root),"python_files":len(rows),"local_import_edges":edges,
            "external_or_unresolved":missing,"entry_points":entries,"process_launches":processes,
            "syntax_faults":syntax,"files":rows,
            "process_policy":"inventory only; inspected Python code is not imported or executed"}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("root",nargs="?",default=".");ap.add_argument("--output",default="python-path-report.json")
    a=ap.parse_args();r=analyze(a.root);Path(a.output).write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({k:r[k] for k in ("python_files","entry_points","process_launches","syntax_faults")},indent=2,default=str))
    raise SystemExit(1 if r["syntax_faults"] else 0)

if __name__=="__main__":main()

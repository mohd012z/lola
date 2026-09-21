"""Lola repository-wide static Python inspection.

Read-only: parses Python sources, builds import/function skeletons, and reports
syntax/import/call issues without executing repository code.
"""
from __future__ import annotations
import ast, json
from pathlib import Path

def inspect_file(path):
    p=Path(path);src=p.read_text(encoding="utf-8",errors="replace")
    try:tree=ast.parse(src)
    except SyntaxError as e:
        return {"file":str(p),"syntax_ok":False,"error":str(e),"line":e.lineno}
    imports=[];defs=[];calls=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.Import):imports += [a.name for a in n.names]
        elif isinstance(n,ast.ImportFrom):imports.append(n.module or "")
        elif isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            defs.append({"type":type(n).__name__,"name":n.name,"line":n.lineno})
        elif isinstance(n,ast.Call):
            f=n.func
            name=f.id if isinstance(f,ast.Name) else f.attr if isinstance(f,ast.Attribute) else None
            if name:calls.append({"name":name,"line":getattr(n,"lineno",None)})
    return {"file":str(p),"syntax_ok":True,"imports":sorted(set(imports)),
            "definitions":defs,"calls":calls[:20000],"lines":src.count("\n")+1}

def inspect_repo(root):
    root=Path(root);rows=[inspect_file(p) for p in sorted(root.glob("*.py"))]
    broken=[x for x in rows if not x["syntax_ok"]]
    return {"python_files":len(rows),"syntax_ok":len(rows)-len(broken),"syntax_broken":len(broken),
            "broken":broken,"files":rows}

def skeleton(report):
    return [{"file":x["file"],"definitions":x.get("definitions",[]),"imports":x.get("imports",[])}
            for x in report["files"]]

def troubleshooting(report):
    issues=[]
    for x in report["files"]:
        if not x["syntax_ok"]:
            issues.append({"severity":"error","file":x["file"],"line":x.get("line"),"issue":"Python syntax error","detail":x.get("error")})
    return issues

def save(report,out):
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True)
    payload={"summary":{"python_files":report["python_files"],"syntax_ok":report["syntax_ok"],
                        "syntax_broken":report["syntax_broken"]},
             "troubleshooting":troubleshooting(report),"skeleton":skeleton(report)}
    p.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    return str(p)

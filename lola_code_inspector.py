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
    root=Path(root);rows=[inspect_file(p) for p in sorted(root.rglob("*.py")) if ".git" not in p.parts]
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


def code_layers(report):
    layers={"interface":[],"dispatch":[],"extract":[],"convert":[],"office":[],"ocr":[],"analysis":[],"runtime":[],"other":[]}
    for x in report["files"]:
        n=Path(x["file"]).name.lower()
        if "dispatcher" in n or "extractor_library" in n:layer="dispatch"
        elif "office" in n:layer="office"
        elif "ocr" in n or "pdf" in n:layer="ocr"
        elif "extract" in n:layer="extract"
        elif "convert" in n:layer="convert"
        elif "inspect" in n or "analy" in n or "preflight" in n:layer="analysis"
        elif "runtime" in n or "frida" in n:layer="runtime"
        elif n in ("lola.py","lola_ui.py","lola_mobile.py"):layer="interface"
        else:layer="other"
        layers[layer].append(x["file"])
    return layers

def code_summary(report):
    return {"python_files":report["python_files"],"syntax_ok":report["syntax_ok"],"syntax_broken":report["syntax_broken"],
            "definitions":sum(len(x.get("definitions",[])) for x in report["files"]),
            "calls":sum(len(x.get("calls",[])) for x in report["files"]),
            "layers":{k:len(v) for k,v in code_layers(report).items()}}

def identify(report,target=None):
    if not target:return [{"file":x["file"],"definitions":len(x.get("definitions",[]))} for x in report["files"]]
    q=target.lower()
    return [x for x in report["files"] if q in x["file"].lower() or any(q in d["name"].lower() for d in x.get("definitions",[]))]

def methods(report,target=None):
    out=[]
    for x in report["files"]:
        if target and target.lower() not in x["file"].lower():continue
        for m in x.get("methods",[]):out.append({"file":x["file"],"name":m["name"],"line":m["line"]})
    return out

def cross_functions(report):
    known={Path(x["file"]).stem for x in report["files"]};rows=[]
    for x in report["files"]:
        local=sorted({i.split(".",1)[0] for i in x.get("imports",[]) if i.split(".",1)[0] in known})
        rows.append({"file":x["file"],"local_imports":local,"calls":sorted({z["name"] for z in x.get("calls",[])})})
    return rows

def run_mode(root,mode,target=None):
    report=inspect_repo(root);mode=(mode or "codecheckall").lower().lstrip("/")
    if mode in ("codecheckall","codecheck","pycheck"):return {"summary":code_summary(report),"issues":troubleshooting(report),"cross":cross_functions(report)}
    if mode=="skeleton":return {"summary":code_summary(report),"skeleton":skeleton(report)}
    if mode=="troubleshooting":return {"summary":code_summary(report),"issues":troubleshooting(report)}
    if mode=="codesummary":return code_summary(report)
    if mode in ("codetarget","codeidentify"):return {"summary":code_summary(report),"matches":identify(report,target)}
    if mode in ("codemethode","codemethod"):return {"summary":code_summary(report),"methods":methods(report,target)}
    if mode in ("codeexpanding","codeextra"):return {"summary":code_summary(report),"expansion":["dispatcher routing","extractor catalog","format adapters","verification diagnostics","bounded processing"]}
    if mode in ("codecodecodelayer","codelayer"):return {"summary":code_summary(report),"layers":code_layers(report),"cross":cross_functions(report)}
    return {"error":"unknown inspection mode","mode":mode}

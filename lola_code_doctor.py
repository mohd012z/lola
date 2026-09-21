"""Lola Code Doctor: repository-wide, non-executing code health bot.

Inspects source/config/document-code formats, applies only conservative text hygiene
fixes when --fix is requested, and emits a machine-readable report. It does not
execute imported targets, guess secrets, bypass protections, or claim semantic
repair when a language-specific compiler is unavailable.
"""
from __future__ import annotations
import argparse, ast, json, re, shutil, subprocess
from pathlib import Path

TEXT_EXT={".py",".js",".mjs",".cjs",".ts",".tsx",".java",".kt",".kts",".c",".h",".cpp",".hpp",
          ".cs",".vb",".vbs",".sh",".ps1",".mq4",".mq5",".smali",".xml",".svg",".css",".html",
          ".htm",".json",".yml",".yaml",".toml",".ini",".cfg",".md",".txt",".csv"}
SKIP={".git",".lola-tools","node_modules","build","dist","__pycache__",".gradle",".idea"}

def files(root):
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT_EXT and not any(x in SKIP for x in p.parts):
            yield p

def _run(argv,cwd):
    try:
        r=subprocess.run(argv,cwd=cwd,capture_output=True,text=True,timeout=90,check=False)
        return {"tool":argv[0],"returncode":r.returncode,"ok":r.returncode==0,
                "stdout":r.stdout[-6000:],"stderr":r.stderr[-6000:]}
    except (OSError,subprocess.TimeoutExpired) as e:
        return {"tool":argv[0],"ok":False,"unavailable":True,"error":str(e)}

def _text_hygiene(path,fix=False):
    raw=path.read_text(encoding="utf-8",errors="replace");issues=[]
    if "\x00" in raw:issues.append("NUL character in text source")
    if any(line.rstrip("\r\n").endswith((" ","\t")) for line in raw.splitlines(True)):
        issues.append("trailing whitespace")
    if "\r\n" in raw:issues.append("CRLF line endings")
    changed=False
    if fix:
        new="\n".join(x.rstrip(" \t\r") for x in raw.split("\n"))
        if raw.endswith("\n") and not new.endswith("\n"):new+="\n"
        if new!=raw:path.write_text(new,encoding="utf-8");changed=True
    return issues,changed

def inspect(path,fix=False):
    ext=path.suffix.lower();issues,changed=_text_hygiene(path,fix)
    checks=[]
    if ext==".py":
        try:ast.parse(path.read_text(encoding="utf-8",errors="replace"));checks.append({"tool":"ast","ok":True})
        except SyntaxError as e:
            checks.append({"tool":"ast","ok":False,"line":e.lineno,"error":str(e)});issues.append("Python syntax error")
    elif ext==".json":
        try:json.loads(path.read_text(encoding="utf-8"));checks.append({"tool":"json","ok":True})
        except Exception as e:checks.append({"tool":"json","ok":False,"error":str(e)});issues.append("invalid JSON")
    elif ext in (".js",".mjs",".cjs") and shutil.which("node"):
        checks.append(_run(["node","--check",str(path)],path.parent))
    elif ext==".sh" and shutil.which("bash"):
        checks.append(_run(["bash","-n",str(path)],path.parent))
    elif ext in (".xml",".svg"):
        try:
            import xml.etree.ElementTree as ET
            ET.parse(path);checks.append({"tool":"xml","ok":True})
        except Exception as e:checks.append({"tool":"xml","ok":False,"error":str(e)});issues.append("invalid XML")
    # Other languages are inventoried and delegated to their compiler/linter adapters when configured.
    failed=[x for x in checks if not x.get("ok")]
    return {"file":str(path),"format":ext.lstrip("."),"issues":issues,"checks":checks,
            "failed_checks":len(failed),"safe_fix_applied":changed}

def run(root=".",fix=False):
    rows=[inspect(p,fix) for p in files(root)]
    by_format={}
    for r in rows:by_format[r["format"]]=by_format.get(r["format"],0)+1
    failures=[r for r in rows if r["issues"] or r["failed_checks"]]
    return {"schema":"Lola-CodeDoctor-1","root":str(Path(root).resolve()),"files":len(rows),
            "formats":by_format,"faults":len(failures),"safe_fixes":sum(r["safe_fix_applied"] for r in rows),
            "status":"attention" if failures else "clear","results":rows,
            "repair_policy":{"automatic":"text hygiene only","semantic":"verify and report; never fabricate a fix",
                             "target_execution":False}}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("root",nargs="?",default=".")
    ap.add_argument("--fix",action="store_true");ap.add_argument("--output",default="code-doctor-report.json")
    a=ap.parse_args();report=run(a.root,a.fix)
    Path(a.output).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("files","formats","faults","safe_fixes","status")},indent=2))
    raise SystemExit(1 if report["faults"] else 0)

if __name__=="__main__":main()

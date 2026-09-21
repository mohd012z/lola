#!/usr/bin/env python3
"""Automatic health gate for Lola bot/coordinator modules.

Performs bounded, non-executing syntax/import/routing checks. It does not launch
external tools, MetaTrader, Frida, Ghidra, or inspected target code.
"""
from __future__ import annotations
import argparse, ast, json, re, sys
from pathlib import Path

BOT_FILES=[
 "lola_code_doctor.py","lola_code_specialists.py","lola_ex_fallback_bots.py",
 "lola_metatrader_bot.py","lola_mt5_mcp_bridge.py","lola_ex_problem_router.py",
 "lola_python_path_doctor.py","lola_python_capabilities.py","lola_workflow_inspector.py",
 "lola_extractor_dispatcher.py","lola_extractor_library.py"
]
REQUIRED_COMMANDS={"/workflow","/head","/skeleton","/troubleshooting","/python","/pytrace",
 "/pylink","/exfallback","/exevidence","/mt5ai","/mt5mcp","/metatrader","/mtcheck","/help"}

def parse_file(p):
    try:
        s=p.read_text(encoding="utf-8-sig",errors="replace")
        ast.parse(s,filename=str(p))
        return {"file":str(p),"ok":True,"literal_escaped_newline":"\\n" in s}
    except Exception as e:return {"file":str(p),"ok":False,"error":str(e)}

def local_imports(root):
    mods={p.stem for p in root.glob("*.py")};missing=[]
    for p in root.glob("*.py"):
        try:t=ast.parse(p.read_text(encoding="utf-8-sig",errors="replace"))
        except Exception:continue
        for n in ast.walk(t):
            names=[]
            if isinstance(n,ast.Import):names=[x.name.split(".")[0] for x in n.names]
            elif isinstance(n,ast.ImportFrom) and n.module:names=[n.module.split(".")[0]]
            for name in names:
                if name.startswith("lola_") and name not in mods:missing.append({"file":p.name,"module":name})
    return missing

def run(root="."):
    root=Path(root).resolve();rows=[]
    for name in BOT_FILES:
        p=root/name
        rows.append(parse_file(p) if p.exists() else {"file":name,"ok":False,"error":"missing bot module"})
    lib=root/"lola_extractor_library.py";commands=set()
    if lib.exists():
        text=lib.read_text(encoding="utf-8",errors="replace")
        commands=set(re.findall(r'"(/[^"]+)":',text))
    missing_commands=sorted(REQUIRED_COMMANDS-commands)
    missing_imports=local_imports(root)
    syntax_fail=[x for x in rows if not x["ok"]]
    # Literal backslash-n is informational because valid Python strings may contain it.
    status="GREEN" if not syntax_fail and not missing_commands and not missing_imports else "RED"
    return {"schema":"Lola-BotHealth-1","status":status,"bots":rows,
            "missing_commands":missing_commands,"missing_local_imports":missing_imports,
            "checks":{"bot_modules":len(rows),"syntax_failures":len(syntax_fail),
                      "required_commands":len(REQUIRED_COMMANDS)},
            "note":"GREEN means static bot health checks passed; external tool/runtime connectivity is reported separately."}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("root",nargs="?",default=".")
    ap.add_argument("--output",default="bot-health-report.json");a=ap.parse_args()
    r=run(a.root);Path(a.output).write_text(json.dumps(r,indent=2),encoding="utf-8")
    print(json.dumps({k:r[k] for k in ("status","checks","missing_commands","missing_local_imports")},indent=2))
    return 0 if r["status"]=="GREEN" else 1
if __name__=="__main__":raise SystemExit(main())

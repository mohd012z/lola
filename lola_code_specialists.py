"""Specialist coordinator for Lola Code Doctor reports.

Routes findings by code family, shows which specialist owns each failure, and
requires a final cross-check before a repair can be considered verified.
"""
from __future__ import annotations
import json
from pathlib import Path

FAMILIES={
 "python":{".py"},"web":{".js",".mjs",".cjs",".ts",".tsx",".html",".htm",".css"},
 "android":{".java",".kt",".kts",".smali"},"native":{".c",".h",".cpp",".hpp"},
 "dotnet":{".cs",".vb",".vbs"},"shell":{".sh",".ps1"},"mql":{".mq4",".mq5"},
 "data":{".json",".xml",".svg",".yml",".yaml",".toml",".ini",".cfg",".csv"},
 "docs":{".md",".txt"}
}

def family(file):
    ext=Path(file).suffix.lower()
    return next((name for name,exts in FAMILIES.items() if ext in exts),"other")

def coordinate(report):
    specialists={k:{"files":0,"faults":0,"items":[]} for k in list(FAMILIES)+["other"]}
    for row in report.get("results",[]):
        f=family(row.get("file",""));s=specialists[f];s["files"]+=1
        bad=bool(row.get("issues") or row.get("failed_checks"))
        if bad:s["faults"]+=1;s["items"].append({"file":row.get("file"),"issues":row.get("issues",[]),"checks":row.get("checks",[])})
    unresolved=sum(x["faults"] for x in specialists.values())
    return {"schema":"Lola-SpecialistCoordinator-1","specialists":specialists,
            "unresolved":unresolved,"final_gate":"pass" if unresolved==0 else "blocked",
            "rule":"A repair is verified only after the owning specialist and final repository check pass."}

def main(report_path="code-doctor-report.json",out="code-specialists.json"):
    report=json.loads(Path(report_path).read_text(encoding="utf-8"))
    result=coordinate(report);Path(out).write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"unresolved":result["unresolved"],"final_gate":result["final_gate"]},indent=2))
    return 1 if result["unresolved"] else 0

if __name__=="__main__":
    import sys
    raise SystemExit(main(*(sys.argv[1:3])))

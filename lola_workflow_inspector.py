"""Workflow/head/skeleton/troubleshooting static coordinator for Lola."""
from __future__ import annotations
import ast, json
from pathlib import Path
from lola_python_path_doctor import analyze
from lola_code_inspector import inspect_repo, skeleton as code_skeleton, troubleshooting as code_troubleshooting

def head(root="."):
    r=analyze(root)
    incoming={}
    for e in r["local_import_edges"]:incoming[e["to"]]=incoming.get(e["to"],0)+1
    heads=sorted(({"file":x["file"],"incoming":incoming.get(x["file"],0),"entry_points":len(x["entry_points"])}
                  for x in r["files"]),key=lambda x:(-x["entry_points"],-x["incoming"],x["file"]))
    return {"schema":"Lola-Head-1","entry_heads":[x for x in heads if x["entry_points"]][:32],
            "dependency_heads":heads[:32]}

def workflow(root="."):
    r=analyze(root);h=head(root)
    return {"schema":"Lola-Workflow-1","heads":h,"edges":r["local_import_edges"],
            "process_launches":r["process_launches"],"entry_points":r["entry_points"],
            "flow":["entry point","dispatcher/router","specialist/static analysis","evidence/result","fallback/help when unresolved"],
            "execution_note":"graph is derived statically; inspected modules are not imported or executed"}

def skeleton(root="."):
    rep=inspect_repo(root)
    return {"schema":"Lola-Skeleton-1","summary":{"python_files":rep["python_files"],"syntax_broken":rep["syntax_broken"]},
            "skeleton":code_skeleton(rep)}

def troubleshooting(root="."):
    p=Path(root);rep=inspect_repo(p);r=analyze(p)
    issues=code_troubleshooting(rep)
    for x in r["external_or_unresolved"]:
        issues.append({"severity":"info","file":x["from"],"issue":"external-or-unresolved import","detail":x["import"]})
    return {"schema":"Lola-Troubleshooting-1","issues":issues,
            "syntax_faults":r["syntax_faults"],"process_launches":r["process_launches"],
            "next":["fix syntax faults first","verify unresolved imports against environment/dependencies",
                    "verify subprocess executable/path availability","re-run workflow and skeleton reports"],
            "automatic_fix_policy":"report first; only conservative text hygiene is auto-fixed elsewhere"}

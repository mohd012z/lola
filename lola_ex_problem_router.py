"""EX4/EX5 evidence-first problem router for Lola.

Builds a bounded troubleshooting bundle from the compiled artifact, nearby
source/reference files, compile logs and MetaTrader journals/tester logs. It can
optionally escalate the bounded packet to the configured MT5 MCP AI. It never
decompiles EX4/EX5 or bypasses protection.
"""
from __future__ import annotations
import hashlib, re
from pathlib import Path
from lola_extractor_core import extract
from lola_mt5_mcp_bridge import ask as ask_mt5

MAX_TEXT=16000
MAX_LOGS=8

def _hash(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def _tail(p,limit=MAX_TEXT):
    try:return p.read_text(encoding="utf-8",errors="replace")[-limit:]
    except Exception:return ""

def _nearby(target,exts):
    p=Path(target);rows=[]
    for x in p.parent.iterdir():
        if x.is_file() and x.suffix.lower() in exts:
            rows.append({"file":str(x),"size":x.stat().st_size,"sha256":_hash(x)})
    return rows[:64]

def _logs(target):
    p=Path(target);patterns=("*.log","*.txt")
    rows=[]
    for pat in patterns:
        for x in sorted(p.parent.glob(pat),key=lambda z:z.stat().st_mtime,reverse=True):
            text=_tail(x)
            if any(k in text.lower() for k in ("error","expert","tester","compile","failed","cannot","invalid","critical")):
                rows.append({"file":str(x),"tail":text})
                if len(rows)>=MAX_LOGS:return rows
    return rows

def diagnose(path,question=None,ask_ai=False):
    p=Path(path);ext=p.suffix.lower()
    if ext not in (".ex4",".ex5"):
        return {"ok":False,"error":"EX4 or EX5 target required"}
    ev=extract(p,include_numbers=False)
    source_ext={".mq4",".mqh"} if ext==".ex4" else {".mq5",".mqh"}
    sources=_nearby(p,source_ext)
    logs=_logs(p)
    observed={"type":"OBSERVED","target":{"file":str(p),"size":p.stat().st_size,"sha256":_hash(p),"extension":ext},
              "signatures":ev.get("signatures",[])[:64],"strings":ev.get("strings",[])[:256]}
    source={"type":"SOURCE","available":bool(sources),"files":sources}
    runtime={"type":"RUNTIME","available":bool(logs),"logs":logs}
    tester={"type":"TESTER","available":any("tester" in x["tail"].lower() for x in logs),
            "note":"Tester evidence is included only when present in selected/local logs."}
    unresolved=[]
    if not sources:unresolved.append("matching MQ4/MQ5/MQH source not found beside artifact")
    if not logs:unresolved.append("no relevant local compile/runtime/tester log found beside artifact")
    packet={"schema":"Lola-EX-Problem-1","question":question or "Diagnose why this compiled MetaTrader artifact fails or behaves unexpectedly.",
            "evidence":[observed,source,runtime,tester],
            "constraints":["evidence-first","no EX4/EX5 decompilation","no protection bypass","label inference separately"],
            "unresolved":unresolved}
    ai=None
    if ask_ai:
        ai=ask_mt5(p,question or "Review this EX4/EX5 evidence and suggest supported diagnostic next steps.")
    return {"ok":True,"packet":packet,"ai":{"type":"AI_SUGGESTION","result":ai} if ask_ai else None,
            "status":"UNRESOLVED" if unresolved else "EVIDENCE_READY",
            "next":{"command":"/help","reason":"; ".join(unresolved),"packet":packet} if unresolved else
                   {"command":"/exaskmt5","reason":"cross-check evidence with configured MT5 AI"}}

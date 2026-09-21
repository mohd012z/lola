"""MetaTrader 4/5 specialist bot for Lola.

Works with user-selected MQL4/MQL5 source. It detects installed MetaEditor,
performs static source checks, can invoke an installed MetaEditor compiler when
explicitly requested, parses compiler logs, and emits /help escalation data for
anything it cannot resolve. It does not decompile or bypass EX4/EX5 protection.
"""
from __future__ import annotations
import re, shutil, subprocess
from pathlib import Path

MAX_SOURCE=8*1024*1024
ENTRY={"mq4":{"OnInit","OnDeinit","OnTick","OnTimer","OnCalculate","OnStart"},
       "mq5":{"OnInit","OnDeinit","OnTick","OnTimer","OnCalculate","OnTrade","OnTradeTransaction","OnStart"}}

def _which(names):
    for n in names:
        p=shutil.which(n)
        if p:return p
    return None

def capabilities():
    editor=_which(["metaeditor64.exe","metaeditor.exe","MetaEditor64.exe","MetaEditor.exe"])
    return {"metaeditor":editor,"mt4_source":True,"mt5_source":True,
            "compiled_binary_policy":"EX4/EX5 may be inventoried as evidence, never decompiled or protection-bypassed"}

def identify(path):
    p=Path(path);ext=p.suffix.lower()
    return {"file":str(p),"platform":"MT4" if ext==".mq4" else "MT5" if ext==".mq5" else None,
            "source":ext in (".mq4",".mq5"),"compiled":ext in (".ex4",".ex5"),"size":p.stat().st_size}

def static_check(path):
    p=Path(path);info=identify(p)
    if not info["source"]:
        return {"ok":False,"target":info,"issues":["MQL source (.mq4/.mq5) required for source validation"],
                "help_required":True,"help":{"command":"/help","reason":"source unavailable or unsupported target"}}
    if info["size"]>MAX_SOURCE:
        return {"ok":False,"target":info,"issues":["source exceeds bounded checker size"],"help_required":True,
                "help":{"command":"/help","reason":"source too large for built-in checker"}}
    s=p.read_text(encoding="utf-8-sig",errors="replace");issues=[];warnings=[]
    # Remove comments/strings only for delimiter sanity checks.
    clean=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',"",s,flags=re.S)
    pairs=[("(",")"),("{","}"),("[","]")]
    for a,b in pairs:
        if clean.count(a)!=clean.count(b):issues.append("unbalanced %s%s delimiters"%(a,b))
    funcs=set(re.findall(r"\b(?:void|int|double|bool|string|datetime|long|color|ENUM_[A-Z0-9_]+)\s+([A-Za-z_]\w*)\s*\(",clean))
    platform="mq4" if p.suffix.lower()==".mq4" else "mq5"
    entry=sorted(funcs & ENTRY[platform])
    if not entry:warnings.append("no standard event handler detected")
    if re.search(r"\bOrderSend\s*\(",clean) and platform=="mq5":
        warnings.append("OrderSend detected in MQ5; verify MqlTradeRequest/MqlTradeResult usage")
    return {"ok":not issues,"target":info,"issues":issues,"warnings":warnings,
            "functions":sorted(funcs)[:10000],"entry_points":entry,
            "help_required":bool(issues),"help":{"command":"/help","reason":"; ".join(issues)} if issues else None}

def compile_source(path,editor=None,timeout=120):
    p=Path(path);pre=static_check(p)
    if not pre["ok"]:return dict(pre,compile_attempted=False)
    editor=editor or capabilities()["metaeditor"]
    if not editor:
        return {"ok":False,"compile_attempted":False,"static":pre,"help_required":True,
                "help":{"command":"/help","reason":"MetaEditor compiler not installed/detected",
                        "needed":"Install/connect MetaTrader 4 or 5 MetaEditor, then retry /mtcompile"}}
    log=p.with_suffix(p.suffix+".compile.log")
    cmd=[editor,"/compile:"+str(p.resolve()),"/log:"+str(log.resolve())]
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as e:
        return {"ok":False,"compile_attempted":True,"static":pre,"error":str(e),"help_required":True,
                "help":{"command":"/help","reason":"MetaEditor compile invocation failed"}}
    text=log.read_text(encoding="utf-16",errors="replace") if log.exists() else (r.stdout+"\n"+r.stderr)
    errors=len(re.findall(r"\berror\b",text,re.I));warnings=len(re.findall(r"\bwarning\b",text,re.I))
    ok=r.returncode==0 and errors==0
    return {"ok":ok,"compile_attempted":True,"returncode":r.returncode,"errors":errors,"warnings":warnings,
            "log":text[-12000:],"static":pre,"help_required":not ok,
            "help":{"command":"/help","reason":"MetaEditor reported compile failure","log_tail":text[-3000:]} if not ok else None}

def help_packet(path=None,reason=None):
    packet={"command":"/help","specialist":"metatrader","request":"resolve unresolved MQL4/MQL5 issue",
            "include":["target platform MT4/MT5","source filename","static-check result","compiler log/error","expected behavior"]}
    if path:
        p=Path(path);packet["target"]=identify(p) if p.exists() and p.is_file() else {"file":str(p)}
    if reason:packet["reason"]=reason
    return packet

def bot(path,compile=False):
    result=compile_source(path) if compile else static_check(path)
    return {"bot":"Lola-MetaTrader-4-5","result":result,
            "next":result.get("help") if result.get("help_required") else {"status":"resolved","action":"final verification"}}

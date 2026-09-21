"""Lola universal static extractor.

Read-only evidence extraction for user-selected files.  It never executes the target,
decrypts protected code, or represents reconstructed text as original source.
"""
from __future__ import annotations
import hashlib, json, math, re, struct
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

WINDOWS=(64,256,1024,4096,16384)
ASCII_RE=re.compile(rb"[\x20-\x7e]{5,}")
URL_RE=re.compile(rb"https?://[^\x00-\x20\x7f]{4,}",re.I)
MQL_SYMBOLS=("OnInit","OnDeinit","OnTick","OnTimer","OnChartEvent","OnCalculate",
"OrderSend","OrderModify","OrderClose","iCustom","iMA","iRSI","iMACD","iBands",
"iStochastic","iIchimoku","ObjectCreate","WebRequest","LoadLibrary")
SCRIPT_MARKERS={"python":("import ","def ","__name__"),"javascript":("function ","require(","=>"),
"vbscript":("CreateObject","Dim ","Sub ","Function "),"shell":("#!/bin/","/bin/sh","/bin/bash"),
"cpp":("std::","__cdecl","__cxa_","operator new")}

def entropy(b:bytes)->float:
    if not b:return 0.0
    c=[0]*256
    for x in b:c[x]+=1
    n=len(b)
    return -sum((v/n)*math.log2(v/n) for v in c if v)

def file_kind(p:Path,data:bytes)->str:
    ext=p.suffix.lower()
    magic=data[:8]
    if ext in (".ex4",".ex5",".mq4",".mq5"):return ext[1:].upper()
    if magic.startswith(b"PK\x03\x04"):return "ZIP/APK"
    if magic.startswith(b"\x7fELF"):return "ELF"
    if magic[:2]==b"MZ":return "PE"
    if magic.startswith(b"%PDF"):return "PDF"
    return ext[1:].upper() if ext else "BINARY"

def strings(data:bytes):
    out=[]
    for m in ASCII_RE.finditer(data):
        s=m.group().decode("ascii","replace")
        out.append({"offset":m.start(),"encoding":"ASCII","value":s})
    # Conservative UTF-16 LE/BE printable runs.
    for endian,pat in (("UTF-16LE",re.compile(rb"(?:[\x20-\x7e]\x00){5,}")),
                       ("UTF-16BE",re.compile(rb"(?:\x00[\x20-\x7e]){5,}"))):
        for m in pat.finditer(data):
            codec="utf-16le" if endian.endswith("LE") else "utf-16be"
            out.append({"offset":m.start(),"encoding":endian,"value":m.group().decode(codec,"replace")})
    return sorted(out,key=lambda x:x["offset"])

def regions(data:bytes):
    out=[]
    for w in WINDOWS:
        for off in range(0,len(data),w):
            b=data[off:off+w]
            if not b:break
            printable=sum(32<=x<=126 for x in b)/len(b)
            zero=b.count(0)/len(b)
            out.append({"offset":off,"size":len(b),"window":w,"entropy":round(entropy(b),5),
                        "printable_ratio":round(printable,5),"zero_ratio":round(zero,5)})
    return out

def numbers(data:bytes,limit=4096):
    out=[]
    end=min(len(data),4*1024*1024)
    for off in range(0,end-8,4):
        for fmt,size,name in (("<f",4,"float32-le"),("<d",8,"float64-le")):
            try:v=struct.unpack_from(fmt,data,off)[0]
            except struct.error:continue
            if math.isfinite(v) and v!=0 and 1e-9<=abs(v)<=1e9:
                out.append({"offset":off,"encoding":name,"value":v})
                if len(out)>=limit:return out
    return out

def classify(rows):
    found=[]
    for row in rows:
        value=row["value"]
        for sym in MQL_SYMBOLS:
            if sym.lower() in value.lower():
                found.append({"offset":row["offset"],"domain":"MQL","symbol":sym,"source":value[:240]})
        for lang,markers in SCRIPT_MARKERS.items():
            if any(x.lower() in value.lower() for x in markers):
                found.append({"offset":row["offset"],"domain":lang.upper(),"symbol":"marker","source":value[:240]})
    return found

def signatures(data:bytes):
    sigs=((b"\x1f\x8b\x08","gzip"),(b"PK\x03\x04","zip"),(b"\x7fELF","elf"),(b"MZ","pe"),
          (b"%PDF","pdf"),(b"SQLite format 3\x00","sqlite"))
    out=[]
    for sig,name in sigs:
        start=0
        while True:
            off=data.find(sig,start)
            if off<0:break
            out.append({"offset":off,"type":name})
            start=off+1
    return out

def extract(path,include_numbers=True):
    p=Path(path);data=p.read_bytes();rows=strings(data)
    return {"schema":"Lola-Evidence360-1","file":p.name,"kind":file_kind(p,data),"size":len(data),
      "sha256":hashlib.sha256(data).hexdigest(),"entropy":round(entropy(data),6),
      "strings":rows,"urls":[{"offset":m.start(),"value":m.group().decode("utf-8","replace")} for m in URL_RE.finditer(data)],
      "regions":regions(data),"numbers":numbers(data) if include_numbers else [],
      "signatures":signatures(data),"code_evidence":classify(rows),
      "policy":{"target_executed":False,"protection_bypass":False,"source_recovery_claim":False}}

def mq_text(report):
    kind=report.get("kind","")
    target="MQ4" if kind=="EX4" else "MQ5" if kind=="EX5" else "TEXT"
    lines=["// Lola evidence-backed reconstruction scaffold",
           "// This is not represented as the original source.","// Target: "+target,""]
    for e in report.get("code_evidence",[])[:500]:
        lines.append("// 0x%X [%s] %s"%(e["offset"],e["domain"],e["symbol"]))
    return "\n".join(lines)+"\n"

def save(report,out_dir):
    d=Path(out_dir);d.mkdir(parents=True,exist_ok=True)
    (d/"evidence360.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    ext=".mq4.txt" if report.get("kind")=="EX4" else ".mq5.txt" if report.get("kind")=="EX5" else ".txt"
    (d/("reconstructed"+ext)).write_text(mq_text(report),encoding="utf-8")
    return d

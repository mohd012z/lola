"""Safe, bounded format/code extraction helpers for Lola.

Archive handlers inventory and extract into a caller-selected workspace with path
traversal protection.  They do not guess passwords or bypass archive protection.
"""
from __future__ import annotations
import base64, binascii, json, re, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_MEMBERS=10000
MAX_TOTAL=512*1024*1024

def decode_base64(text:str):
    try:return {"ok":True,"bytes":base64.b64decode(text,validate=True)}
    except (binascii.Error,ValueError) as e:return {"ok":False,"error":str(e)}

def decode_base44(text:str):
    return {"ok":False,"supported":False,"note":"Base44 is not treated as a standard codec. Register an explicit documented codec before decoding."}

def zip_inventory(path):
    with zipfile.ZipFile(path) as z:
        rows=[]
        for i,x in enumerate(z.infolist()):
            if i>=MAX_MEMBERS:break
            rows.append({"name":x.filename,"size":x.file_size,"compressed":x.compress_size,"crc":x.CRC})
        return rows

def safe_zip_extract(path,out):
    root=Path(out).resolve();root.mkdir(parents=True,exist_ok=True);total=0;written=[]
    with zipfile.ZipFile(path) as z:
        for i,x in enumerate(z.infolist()):
            if i>=MAX_MEMBERS:break
            total+=x.file_size
            if total>MAX_TOTAL:raise ValueError("Archive exceeds extraction limit")
            dst=(root/x.filename).resolve()
            if root!=dst and root not in dst.parents:continue
            if x.is_dir():dst.mkdir(parents=True,exist_ok=True);continue
            dst.parent.mkdir(parents=True,exist_ok=True)
            with z.open(x) as src,open(dst,"wb") as f:
                while True:
                    b=src.read(1024*1024)
                    if not b:break
                    f.write(b)
            written.append(str(dst))
    return written

def rar_inventory(path):
    try:
        import rarfile
        with rarfile.RarFile(path) as r:return [{"name":x.filename,"size":x.file_size} for x in r.infolist()[:MAX_MEMBERS]]
    except ImportError:return [{"supported":False,"note":"Install optional rarfile plus an available RAR backend."}]

def sevenzip_inventory(path):
    try:
        import py7zr
        with py7zr.SevenZipFile(path,"r") as z:return [{"name":x} for x in z.getnames()[:MAX_MEMBERS]]
    except ImportError:return [{"supported":False,"note":"Install optional py7zr."}]

def xml_summary(path):
    root=ET.parse(path).getroot();counts={}
    for e in root.iter():counts[e.tag]=counts.get(e.tag,0)+1
    return {"root":root.tag,"elements":counts}

def svg_summary(path):
    x=xml_summary(path);x["format"]="SVG";return x

def css_tokens(text):
    selectors=re.findall(r"([^{}]+)\{",text)
    props=re.findall(r"([\w-]+)\s*:",text)
    return {"selectors":[x.strip() for x in selectors[:2000]],"properties":props[:10000]}

def code_chunks(data:bytes,size=4096):
    size=max(64,min(int(size),1024*1024))
    return [{"offset":o,"size":len(data[o:o+size])} for o in range(0,len(data),size)]

def blob_summary(data:bytes):
    return {"size":len(data),"head_hex":data[:128].hex(),"zero_bytes":data.count(0)}

def semgrep_plan(path):
    return {"tool":"semgrep","target":str(path),"mode":"static-source","note":"Run only on user-selected source/workspace; results are evidence, not target execution."}

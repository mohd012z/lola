"""Extended bounded static format extractors for Lola."""
from __future__ import annotations
import json, sqlite3, struct, zipfile
from pathlib import Path

def dex_summary(path):
    b=Path(path).read_bytes();ok=len(b)>=112 and b[:4]==b"dex\n"
    if not ok:return {"format":"DEX","valid":False}
    u=lambda o:struct.unpack_from("<I",b,o)[0]
    return {"format":"DEX","valid":True,"version":b[4:7].decode("ascii","replace"),
      "file_size":u(32),"header_size":u(36),"endian_tag":hex(u(40)),
      "string_ids":u(56),"type_ids":u(64),"proto_ids":u(72),"field_ids":u(80),
      "method_ids":u(88),"class_defs":u(96),"data_size":u(104),"data_off":u(108)}

def class_summary(path):
    b=Path(path).read_bytes()
    if len(b)<10 or b[:4]!=b"\xca\xfe\xba\xbe":return {"format":"JAVA_CLASS","valid":False}
    minor,major,cp=struct.unpack_from(">HHH",b,4)
    return {"format":"JAVA_CLASS","valid":True,"minor":minor,"major":major,"constant_pool_count":cp}

def wasm_summary(path):
    b=Path(path).read_bytes()
    if len(b)<8 or b[:4]!=b"\x00asm":return {"format":"WASM","valid":False}
    return {"format":"WASM","valid":True,"version":int.from_bytes(b[4:8],"little"),"size":len(b)}

def json_summary(path):
    obj=json.loads(Path(path).read_text(encoding="utf-8",errors="strict"))
    if isinstance(obj,dict):return {"format":"JSON","root":"object","keys":list(obj)[:2000],"count":len(obj)}
    if isinstance(obj,list):return {"format":"JSON","root":"array","count":len(obj)}
    return {"format":"JSON","root":type(obj).__name__}

def sqlite_summary(path):
    p=Path(path)
    if p.read_bytes()[:16]!=b"SQLite format 3\x00":return {"format":"SQLITE","valid":False}
    # Read-only URI; schema only, never execute statements sourced from the database.
    con=sqlite3.connect("file:"+str(p.resolve())+"?mode=ro",uri=True)
    try:
        rows=con.execute("SELECT type,name,tbl_name FROM sqlite_master ORDER BY type,name").fetchall()
        return {"format":"SQLITE","valid":True,"objects":[{"type":a,"name":b,"table":c} for a,b,c in rows[:10000]]}
    finally:con.close()

def zip_package_summary(path,label="ZIP_PACKAGE"):
    with zipfile.ZipFile(path) as z:
        rows=[]
        for x in z.infolist()[:10000]:
            rows.append({"name":x.filename,"size":x.file_size,"compressed":x.compress_size})
        return {"format":label,"members":rows,"count":len(z.infolist())}

def protobuf_wire_summary(path,limit=10000):
    # Generic protobuf wire inventory only; schema-less values are not assigned semantic names.
    b=Path(path).read_bytes();i=0;rows=[]
    def varint(pos):
        v=0;s=0
        while pos<len(b) and s<70:
            x=b[pos];pos+=1;v|=(x&127)<<s
            if not x&128:return v,pos
            s+=7
        raise ValueError
    try:
        while i<len(b) and len(rows)<limit:
            key,i2=varint(i);field=key>>3;wire=key&7;i=i2;start=i2
            if field==0 or wire not in (0,1,2,5):break
            if wire==0:_,i=varint(i)
            elif wire==1:i+=8
            elif wire==5:i+=4
            else:
                n,i=varint(i);i+=n
            if i>len(b):break
            rows.append({"field":field,"wire":wire,"offset":start,"end":i})
    except (ValueError,IndexError):pass
    return {"format":"PROTOBUF_WIRE","schema_known":False,"fields":rows,"parsed_bytes":i,"size":len(b)}

def extended_summary(path):
    p=Path(path);ext=p.suffix.lower();head=p.read_bytes()[:16]
    if head[:4]==b"dex\n":return dex_summary(p)
    if head[:4]==b"\xca\xfe\xba\xbe":return class_summary(p)
    if head[:4]==b"\x00asm":return wasm_summary(p)
    if head==b"SQLite format 3\x00":return sqlite_summary(p)
    if ext==".json":return json_summary(p)
    if ext in (".jar",".apk",".aab"):return zip_package_summary(p,ext[1:].upper())
    if ext in (".pb",".protobuf",".proto.bin"):return protobuf_wire_summary(p)
    if ext in (".pak",".img",".iso"):return {"format":ext[1:].upper(),"mode":"raw-container","note":"Use signature carving/chunk/entropy analysis; no filesystem format is assumed from extension alone."}
    return {"format":"UNKNOWN_EXTENDED","extension":ext}

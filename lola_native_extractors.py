"""Bounded PE/ELF/DAT static evidence for Lola.

Pure parsing only: no loading, execution, injection, patching, or protection bypass.
"""
from __future__ import annotations
import struct
from pathlib import Path

def _u16(b,o): return struct.unpack_from("<H",b,o)[0] if o+2<=len(b) else None
def _u32(b,o): return struct.unpack_from("<I",b,o)[0] if o+4<=len(b) else None
def _u64(b,o): return struct.unpack_from("<Q",b,o)[0] if o+8<=len(b) else None

def pe_summary(path):
    b=Path(path).read_bytes()
    out={"format":"PE","valid":False,"sections":[]}
    if len(b)<0x40 or b[:2]!=b"MZ": return out
    pe=_u32(b,0x3c)
    if pe is None or pe+24>len(b) or b[pe:pe+4]!=b"PE\0\0": return out
    machine=_u16(b,pe+4);nsec=_u16(b,pe+6) or 0;opt=_u16(b,pe+20) or 0
    out.update(valid=True,machine=machine,section_count=nsec,optional_header_size=opt)
    sec=pe+24+opt
    for i in range(min(nsec,96)):
        o=sec+i*40
        if o+40>len(b):break
        name=b[o:o+8].split(b"\0",1)[0].decode("ascii","replace")
        out["sections"].append({"name":name,"virtual_size":_u32(b,o+8),"virtual_address":_u32(b,o+12),
          "raw_size":_u32(b,o+16),"raw_offset":_u32(b,o+20),"characteristics":_u32(b,o+36)})
    return out

def elf_summary(path):
    b=Path(path).read_bytes()
    out={"format":"ELF","valid":False,"sections":[]}
    if len(b)<0x34 or b[:4]!=b"\x7fELF":return out
    cls=b[4];end=b[5]
    if end not in (1,2):return out
    e="<" if end==1 else ">"
    try:
        machine=struct.unpack_from(e+"H",b,18)[0]
        if cls==1:
            shoff=struct.unpack_from(e+"I",b,32)[0];shents=struct.unpack_from(e+"H",b,46)[0];shnum=struct.unpack_from(e+"H",b,48)[0]
        elif cls==2:
            shoff=struct.unpack_from(e+"Q",b,40)[0];shents=struct.unpack_from(e+"H",b,58)[0];shnum=struct.unpack_from(e+"H",b,60)[0]
        else:return out
    except struct.error:return out
    out.update(valid=True,bits=32 if cls==1 else 64,endian="little" if end==1 else "big",machine=machine,
               section_count=shnum,section_table_offset=shoff)
    for i in range(min(shnum,256)):
        o=shoff+i*shents
        if o+shents>len(b):break
        try:
            if cls==1:
                typ=struct.unpack_from(e+"I",b,o+4)[0];off=struct.unpack_from(e+"I",b,o+16)[0];size=struct.unpack_from(e+"I",b,o+20)[0]
            else:
                typ=struct.unpack_from(e+"I",b,o+4)[0];off=struct.unpack_from(e+"Q",b,o+24)[0];size=struct.unpack_from(e+"Q",b,o+32)[0]
            out["sections"].append({"index":i,"type":typ,"offset":off,"size":size})
        except struct.error:break
    return out

def dat_summary(path):
    p=Path(path);b=p.read_bytes()
    return {"format":"DAT/RAW","size":len(b),"head_hex":b[:256].hex(),
            "tail_hex":b[-128:].hex() if b else "","note":"DAT is extension-generic; content is classified by magic/evidence."}

def native_summary(path):
    p=Path(path);b=p.read_bytes()[:8]
    if b[:2]==b"MZ":return pe_summary(p)
    if b[:4]==b"\x7fELF":return elf_summary(p)
    return dat_summary(p)

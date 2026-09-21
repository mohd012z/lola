"""Command dispatcher for Lola managed extraction library."""
from pathlib import Path
from lola_extractor_core import extract
from lola_format_extractors import *
from lola_extractor_library import resolve, catalog
from lola_deep_extractor import deep_extract, graph
from lola_native_extractors import native_summary

def run(command,target=None,arg=None):
    mod=resolve(command)
    if not mod:return {"ok":False,"error":"unknown command","command":command}
    if command=="/codecli":return {"ok":True,"modules":catalog()}
    if command in ("/deep-dive","/*.***","/*.**") and target is not None:
        node=deep_extract(target)
        return {"ok":True,"mode":"recursive-deep","root":node,"graph":graph(node)}
    if target is None:return {"ok":True,"module":mod}
    p=Path(target)
    if not p.is_file():return {"ok":False,"error":"target is not a readable file"}
    if command in ("/*.exe","/*.dll","/*.so","/*.elf","/*.dat","/*.bin"):
        return {"ok":True,"module":mod,"native":native_summary(p),"evidence":extract(p)}
    if command=="/base64":
        return decode_base64(p.read_text(encoding="utf-8",errors="replace").strip())
    if command=="/base44":return decode_base44(p.read_text(encoding="utf-8",errors="replace").strip())
    if command=="/zip":return {"ok":True,"inventory":zip_inventory(p)}
    if command=="/rar":return {"ok":True,"inventory":rar_inventory(p)}
    if command=="/7zip":return {"ok":True,"inventory":sevenzip_inventory(p)}
    if command=="/xml":return {"ok":True,"summary":xml_summary(p)}
    if command=="/svg":return {"ok":True,"summary":svg_summary(p)}
    if command=="/css":return {"ok":True,"summary":css_tokens(p.read_text(encoding="utf-8",errors="replace"))}
    if command=="/blob":return {"ok":True,"summary":blob_summary(p.read_bytes())}
    if command=="/chunk":return {"ok":True,"chunks":code_chunks(p.read_bytes(),int(arg or 4096))}
    if command in ("/smgrep","/semgrep"):return {"ok":True,"plan":semgrep_plan(p)}
    # C/C++, vector, format/wildcard and the broader library feed the universal evidence core.
    return {"ok":True,"module":mod,"evidence":extract(p)}

"""Higher-fidelity Office styling helpers for Lola HTML export."""
from __future__ import annotations
import base64, html
from pathlib import Path

def color(v,default=""):
    if not v:return default
    rgb=getattr(v,"rgb",None)
    if rgb and isinstance(rgb,str) and len(rgb)>=6:return "#"+rgb[-6:]
    return default

def xlsx_style(cell):
    s=[]
    f=cell.font
    if f:
        if f.bold:s.append("font-weight:700")
        if f.italic:s.append("font-style:italic")
        if f.sz:s.append("font-size:%spt"%f.sz)
        c=color(f.color)
        if c:s.append("color:"+c)
    fill=getattr(cell,"fill",None)
    if fill and getattr(fill,"fill_type",None):
        c=color(getattr(fill,"fgColor",None))
        if c:s.append("background:"+c)
    a=cell.alignment
    if a:
        if a.horizontal:s.append("text-align:"+a.horizontal)
        if a.vertical:s.append("vertical-align:"+a.vertical)
        if a.wrap_text:s.append("white-space:normal")
    return ";".join(s)

def xlsx_images(ws):
    out=[]
    for im in getattr(ws,"_images",[]):
        try:
            blob=im._data();fmt=(getattr(im,"format",None) or "png").lower()
            mime="image/jpeg" if fmt in ("jpg","jpeg") else "image/"+fmt
            uri="data:"+mime+";base64,"+base64.b64encode(blob).decode("ascii")
            anchor=getattr(im,"anchor",None);cell=""
            if hasattr(anchor,"_from"):
                cell="%s%d"%(chr(65+anchor._from.col),anchor._from.row+1) if anchor._from.col<26 else ""
            out.append("<figure class='sheet-image' data-anchor='"+html.escape(cell)+"'><img loading='lazy' src='"+uri+"'></figure>")
        except Exception:continue
    return "".join(out)

def dimensions_css(ws):
    rules=[]
    for key,d in ws.column_dimensions.items():
        if d.width:rules.append("/* column %s width %.2f */"%(key,d.width))
    return "".join(rules)

def docx_headers_footers(doc):
    parts=[]
    for si,sec in enumerate(doc.sections,1):
        h=" ".join(p.text for p in sec.header.paragraphs if p.text.strip())
        f=" ".join(p.text for p in sec.footer.paragraphs if p.text.strip())
        if h:parts.append("<div class='doc-header' data-section='%d'>%s</div>"%(si,html.escape(h)))
        if f:parts.append("<div class='doc-footer' data-section='%d'>%s</div>"%(si,html.escape(f)))
    return "".join(parts)

def hyperlink_map(paragraph):
    # python-docx does not expose every hyperlink as a normal run; inspect relationships.
    rels=paragraph.part.rels;out=[]
    for child in paragraph._p.iterchildren():
        tag=child.tag.rsplit("}",1)[-1]
        if tag=="hyperlink":
            rid=child.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            text="".join(n.text or "" for n in child.iter() if n.tag.rsplit("}",1)[-1]=="t")
            target=rels[rid].target_ref if rid in rels else ""
            if target:out.append((text,target))
    return out

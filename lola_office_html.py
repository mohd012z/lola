"""Office document -> HTML conversion engine for Lola.

Produces self-contained or asset-folder HTML from user-selected office documents.
Prefers semantic HTML for DOCX/XLSX and page-faithful reconstruction for PDF.
"""
from __future__ import annotations
import base64, html, mimetypes
from pathlib import Path

def _page(title,body,extra_css=""):
    css="""*{box-sizing:border-box}body{font-family:system-ui,Arial,sans-serif;margin:0;background:#f5f6f8;color:#171717}
main{max-width:1100px;margin:auto;background:white;min-height:100vh;padding:24px}
table{border-collapse:collapse;width:100%;margin:16px 0}th,td{border:1px solid #bbb;padding:6px;vertical-align:top}
img{max-width:100%;height:auto}.sheet{overflow:auto;margin:18px 0}.page{margin:0 0 28px}.page-break{break-after:page}
pre{white-space:pre-wrap}""" + extra_css
    return "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>"+html.escape(title)+"</title><style>"+css+"</style></head><body><main>"+body+"</main></body></html>"

def _save(dst,text):
    p=Path(dst);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding="utf-8")
    return {"ok":True,"output":str(p)}

def txt_to_html(src,dst):
    p=Path(src);body="<pre>"+html.escape(p.read_text(encoding="utf-8",errors="replace"))+"</pre>"
    return _save(dst,_page(p.name,body))

def csv_to_html(src,dst):
    import csv
    rows=[]
    with open(src,newline="",encoding="utf-8-sig",errors="replace") as f:
        for row in csv.reader(f):rows.append("<tr>"+"".join("<td>"+html.escape(v)+"</td>" for v in row)+"</tr>")
    return _save(dst,_page(Path(src).name,"<table>"+"".join(rows)+"</table>"))

def xlsx_to_html(src,dst):
    from openpyxl import load_workbook
    wb=load_workbook(src,data_only=False,read_only=True);parts=[]
    for ws in wb.worksheets:
        rows=[]
        for row in ws.iter_rows(values_only=False):
            cells=[]
            for cell in row:
                value=cell.value
                if value is None:s=""
                elif isinstance(value,str) and value.startswith("="):s=value
                else:s=str(value)
                cells.append("<td>"+html.escape(s)+"</td>")
            rows.append("<tr>"+"".join(cells)+"</tr>")
        parts.append("<section class='sheet'><h2>"+html.escape(ws.title)+"</h2><table>"+"".join(rows)+"</table></section>")
    return _save(dst,_page(Path(src).name,"".join(parts)))

def docx_to_html(src,dst):
    from docx import Document
    doc=Document(src);parts=[]
    # Preserve document order for paragraphs/tables.
    for child in doc.element.body.iterchildren():
        tag=child.tag.rsplit("}",1)[-1]
        if tag=="p":
            texts=[n.text or "" for n in child.iter() if n.tag.rsplit("}",1)[-1]=="t"]
            text="".join(texts)
            if text:parts.append("<p>"+html.escape(text)+"</p>")
        elif tag=="tbl":
            rows=[]
            for tr in [x for x in child if x.tag.rsplit("}",1)[-1]=="tr"]:
                cells=[]
                for tc in [x for x in tr if x.tag.rsplit("}",1)[-1]=="tc"]:
                    texts=[n.text or "" for n in tc.iter() if n.tag.rsplit("}",1)[-1]=="t"]
                    cells.append("<td>"+html.escape("".join(texts))+"</td>")
                rows.append("<tr>"+"".join(cells)+"</tr>")
            parts.append("<table>"+"".join(rows)+"</table>")
    return _save(dst,_page(Path(src).name,"".join(parts)))

def pdf_to_html(src,dst):
    import fitz
    pdf=fitz.open(src);parts=[]
    for i,page in enumerate(pdf):
        blocks=page.get_text("blocks")
        body="".join("<p>"+html.escape((b[4] or "").strip()).replace("\n","<br>")+"</p>" for b in blocks if (b[4] or "").strip())
        parts.append("<section class='page' data-page='"+str(i+1)+"'><h2>Page "+str(i+1)+"</h2>"+body+"</section>")
    return _save(dst,_page(Path(src).name,"".join(parts)))

def convert(src,dst):
    ext=Path(src).suffix.lower()
    if ext in (".txt",".md",".log"):return txt_to_html(src,dst)
    if ext==".csv":return csv_to_html(src,dst)
    if ext==".xlsx":return xlsx_to_html(src,dst)
    if ext==".docx":return docx_to_html(src,dst)
    if ext==".pdf":return pdf_to_html(src,dst)
    return {"ok":False,"error":"Direct HTML adapter not registered","source":ext,
            "fallback":"convert legacy office format to DOCX/XLSX first, then HTML"}

def matrix():
    return {"direct":["DOCX->HTML","XLSX->HTML","CSV->HTML","TXT/MD/LOG->HTML","PDF->HTML"],
            "staged":["DOC->DOCX->HTML","ODT->DOCX->HTML","XLS->XLSX->HTML","ODS->XLSX->HTML"],
            "html_features":["responsive viewport","semantic tables","sheet sections","PDF page provenance","escaped source text"]}

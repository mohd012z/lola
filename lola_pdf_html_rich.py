"""Rich PDF/OCR -> interactive HTML renderer for Lola."""
from __future__ import annotations
import base64, html
from pathlib import Path
from lola_office_html_rich import interactive_shell

def _uri(blob,mime="image/png"):
    return "data:"+mime+";base64,"+base64.b64encode(blob).decode("ascii")

def pdf_rich(src,dst,dpi=144,ocr=False,lang="eng"):
    import fitz
    pdf=fitz.open(src);parts=[];ocr_pages=0
    pyt=None;Image=None
    if ocr:
        try:
            import pytesseract as pyt
            from PIL import Image
        except ImportError:pass
    scale=max(1.0,min(dpi/72.0,4.0))
    for i,page in enumerate(pdf):
        text=page.get_text("text").strip();mode="text"
        # Render a faithful visual page; searchable text is retained below it.
        pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
        png=pix.tobytes("png")
        if len(text)<40 and pyt and Image:
            img=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
            text=pyt.image_to_string(img,lang=lang).strip();mode="ocr";ocr_pages+=1
        safe=html.escape(text).replace("\n","<br>")
        parts.append("<section class='pdf-page' data-page='%d' data-text-mode='%s'><header>Page %d · %s</header><img loading='lazy' class='pdf-image' src='%s' alt='PDF page %d'><div class='pdf-text'>%s</div></section>"%(i+1,mode,i+1,mode.upper(),_uri(png),i+1,safe))
    body="<nav class='page-nav'>"+ "".join("<a href='#p%d'>%d</a>"%(i,i) for i in range(1,len(pdf)+1))+"</nav>"
    # Add IDs without duplicating another pass over PDF.
    body+="".join(x.replace("class='pdf-page'","id='p%d' class='pdf-page'"%(i+1),1) for i,x in enumerate(parts))
    shell=interactive_shell(Path(src).name,body)
    shell=shell.replace("</style>",""" .pdf-page{margin:18px auto 34px;max-width:1000px;border:1px solid #bbb;background:#fff;box-shadow:0 2px 10px #0002}.pdf-page header{padding:7px 10px;background:#f0f2f4;font-weight:600}.pdf-image{display:block;width:100%}.pdf-text{padding:12px;line-height:1.45}.page-nav{display:flex;gap:5px;overflow:auto;position:sticky;top:48px;background:white;padding:6px;z-index:8}.page-nav a{padding:5px 8px;border:1px solid #aaa;text-decoration:none}@media print{.page-nav,.pdf-text{display:none}.pdf-page{break-after:page;box-shadow:none;border:0}} </style>""")
    p=Path(dst);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(shell,encoding="utf-8")
    return {"ok":True,"output":str(p),"pages":len(pdf),"ocr_pages":ocr_pages,"dpi":dpi,"language":lang}

def batch_convert(folder,out_dir,recursive=False,ocr_pdf=False):
    from lola_office_html import convert
    root=Path(folder);out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    iterator=root.rglob("*") if recursive else root.glob("*");results=[]
    allowed={".docx",".xlsx",".csv",".txt",".md",".log",".pdf"}
    for p in iterator:
        if not p.is_file() or p.suffix.lower() not in allowed:continue
        rel=p.relative_to(root);dst=(out/rel).with_suffix(".html");dst.parent.mkdir(parents=True,exist_ok=True)
        try:r=pdf_rich(p,dst,ocr=ocr_pdf) if p.suffix.lower()==".pdf" else convert(p,dst)
        except Exception as e:r={"ok":False,"error":str(e)}
        r["source"]=str(p);results.append(r)
    return {"ok":all(x.get("ok") for x in results) if results else True,"count":len(results),"results":results}

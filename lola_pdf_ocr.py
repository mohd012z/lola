"""OCR pipeline for scanned/searchable PDFs in Lola.

Read-only input analysis. OCR is performed only on rendered page images in the
workspace. Original PDFs are never modified unless a caller explicitly creates a
new output PDF.
"""
from __future__ import annotations
import shutil, subprocess
from pathlib import Path

def capabilities():
    mods={}
    for n in ("fitz","pytesseract","PIL"):
        try:__import__(n);mods[n]=True
        except ImportError:mods[n]=False
    mods["tesseract"]=bool(shutil.which("tesseract"))
    mods["ocrmypdf"]=bool(shutil.which("ocrmypdf"))
    return mods

def readiness(path):
    import fitz
    pdf=fitz.open(path);rows=[];total_chars=0
    for i,page in enumerate(pdf):
        text=page.get_text("text").strip();chars=len(text);total_chars+=chars
        images=len(page.get_images(full=True))
        rows.append({"page":i+1,"text_chars":chars,"images":images,
                     "ocr_recommended":chars<40 and images>0})
    need=sum(1 for x in rows if x["ocr_recommended"])
    return {"pages":len(pdf),"text_chars":total_chars,"ocr_pages":need,
            "searchable_pages":len(pdf)-need,"page_status":rows,
            "classification":"scanned-or-mixed" if need else "searchable-text"}

def ocr_pages(path,out_dir,dpi=200,lang="eng"):
    import fitz, pytesseract
    from PIL import Image
    pdf=fitz.open(path);out=Path(out_dir);out.mkdir(parents=True,exist_ok=True);results=[]
    scale=max(1.0,min(float(dpi)/72.0,5.0));matrix=fitz.Matrix(scale,scale)
    for i,page in enumerate(pdf):
        existing=page.get_text("text").strip()
        if len(existing)>=40:
            results.append({"page":i+1,"mode":"existing-text","text":existing});continue
        pix=page.get_pixmap(matrix=matrix,alpha=False)
        img=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
        text=pytesseract.image_to_string(img,lang=lang)
        txt=out/("page-%04d.txt"%(i+1));txt.write_text(text,encoding="utf-8")
        results.append({"page":i+1,"mode":"ocr","text":text,"text_file":str(txt)})
    return {"pages":results,"dpi":dpi,"language":lang}

def searchable_pdf(src,dst,lang="eng"):
    exe=shutil.which("ocrmypdf")
    if not exe:return {"ok":False,"missing":"ocrmypdf",
      "note":"Install OCRmyPDF for a new searchable PDF with an OCR text layer."}
    dst=Path(dst);dst.parent.mkdir(parents=True,exist_ok=True)
    p=subprocess.run([exe,"--skip-text","--deskew","--rotate-pages","-l",lang,str(src),str(dst)],
                     capture_output=True,text=True,timeout=900,check=False)
    return {"ok":p.returncode==0,"output":str(dst),"returncode":p.returncode,
            "stdout":p.stdout[-12000:],"stderr":p.stderr[-12000:]}

def workflow(path):
    return {"input":str(path),"readiness":readiness(path),"capabilities":capabilities(),
      "pipeline":["detect searchable vs scanned per page","OCR only pages needing OCR",
                  "preserve page number provenance","export page text + combined evidence",
                  "optionally create a new searchable PDF","feed OCR text into DOCX/XLSX extraction"]}

"""Document conversion planner for Lola.

Focuses on editable office-document workflows.  PDF is page-oriented, so PDF to
DOCX/XLSX is extraction/reconstruction rather than guaranteed lossless conversion.
"""
from __future__ import annotations
import shutil
from pathlib import Path

FORMATS={"pdf","doc","docx","odt","rtf","txt","html","xls","xlsx","ods","csv"}

def tools():
    return {n:shutil.which(n) for n in ("libreoffice","soffice","pandoc","python","python3")}

def family(ext):
    e=ext.lower().lstrip(".")
    if e=="pdf":return "pdf"
    if e in ("doc","docx","odt","rtf","txt","html"):return "word"
    if e in ("xls","xlsx","ods","csv"):return "sheet"
    return "unknown"

def conversion_plan(path,target):
    p=Path(path);src=p.suffix.lower().lstrip(".");dst=target.lower().lstrip(".")
    if src not in FORMATS or dst not in FORMATS:
        return {"supported":False,"source":src,"target":dst,"reason":"format-not-registered"}
    sf,df=family(src),family(dst)
    if sf=="pdf" and df=="word":
        route=["PyMuPDF: text/layout/images","OCR fallback for scanned pages","python-docx: editable DOCX"]
        quality="reconstructed-editable"
    elif sf=="pdf" and df=="sheet":
        route=["PyMuPDF/pdfplumber: table detection","table validation","openpyxl: XLSX worksheets"]
        quality="table-reconstruction"
    elif sf in ("word","sheet") and df=="pdf":
        route=["LibreOffice headless export when available","native Python fallback for supported generated documents"]
        quality="rendered"
    elif sf=="word" and df=="sheet":
        route=["extract document tables","openpyxl: one or more worksheets"]
        quality="structured-table-extraction"
    elif sf=="sheet" and df=="word":
        route=["read workbook cells/tables","python-docx: editable tables"]
        quality="structured-table-reconstruction"
    else:
        route=["LibreOffice/Pandoc compatible conversion","Python library fallback"]
        quality="format-conversion"
    return {"supported":True,"source":src,"target":dst,"source_family":sf,"target_family":df,
            "route":route,"quality":quality,"tools":tools(),
            "note":"PDF reconstruction may not preserve exact fonts, pagination, merged cells, or reading order."}

def matrix():
    return [
      {"from":"PDF","to":"DOCX","method":"layout/text/image extraction + DOCX reconstruction"},
      {"from":"PDF","to":"XLSX","method":"table detection/extraction + workbook reconstruction"},
      {"from":"DOC/DOCX/ODT","to":"PDF","method":"office renderer/export"},
      {"from":"XLS/XLSX/ODS","to":"PDF","method":"office renderer/export"},
      {"from":"DOCX","to":"XLSX","method":"table extraction"},
      {"from":"XLSX","to":"DOCX","method":"worksheet-to-editable-table reconstruction"},
      {"from":"CSV","to":"XLSX","method":"structured rows/cells"},
      {"from":"XLSX","to":"CSV","method":"selected-sheet structured export"},
    ]

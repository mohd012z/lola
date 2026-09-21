"""Command dispatcher for Lola managed extraction library."""
from pathlib import Path
from lola_extractor_core import extract
from lola_format_extractors import *
from lola_extractor_library import resolve, catalog
from lola_deep_extractor import deep_extract, graph
from lola_native_extractors import native_summary
from lola_extended_extractors import extended_summary
from lola_universal_converter import detect as detect_format, python_summary, plan as conversion_plan, available_tools
from lola_document_converter import conversion_plan as document_conversion_plan, matrix as document_matrix
from lola_office_engine import capabilities as office_capabilities, convert as office_convert
from lola_office_html import convert as html_convert, matrix as html_matrix
from lola_pdf_html_rich import pdf_rich, batch_convert
from lola_pdf_ocr import capabilities as ocr_capabilities, readiness as ocr_readiness, ocr_pages, searchable_pdf\nfrom lola_code_inspector import run_mode as code_inspect

def run(command,target=None,arg=None):
    cmd=(command or "").strip().lower()
    mod=resolve(cmd)
    if not mod:return {"ok":False,"error":"unknown command","command":command}
    if cmd=="/codecli":return {"ok":True,"modules":catalog()}\n    inspect_cmds={"/codecheckall","/codetarget","/codeidentify","/codemethode","/codemethod","/codeexpanding","/codeextra","/codecodecodelayer","/codelayer","/skeleton","/troubleshooting","/codesummary","/codecheck","/pycheck"}\n    if cmd in inspect_cmds:\n        root=Path(target or ".")\n        if not root.exists():return {"ok":False,"error":"inspection target does not exist"}\n        # arg narrows file/definition matching for target/method modes.\n        return {"ok":True,"mode":cmd[1:],"inspection":code_inspect(root,cmd,arg)}
    if cmd=="/officecapabilities":return {"ok":True,"office":office_capabilities(),"ocr":ocr_capabilities()}
    if cmd=="/documentconvert" and target is None:
        return {"ok":True,"module":mod,"matrix":document_matrix(),"tools":available_tools()}
    if cmd in ("/office2html","/document2html") and target is None:
        return {"ok":True,"module":mod,"matrix":html_matrix()}
    if cmd in ("/deep-dive","/*.***","/*.**") and target is not None:
        node=deep_extract(target)
        return {"ok":True,"mode":"recursive-deep","root":node,"graph":graph(node)}
    if target is None:return {"ok":True,"module":mod}
    p=Path(target)
    # Folder batch conversion is the only route that intentionally accepts a directory.
    if cmd in ("/batchofficehtml","/folder2html"):
        if not p.is_dir():return {"ok":False,"error":"target is not a readable folder"}
        if not arg:return {"ok":False,"error":"output folder required in arg"}
        return batch_convert(p,arg)
    if not p.is_file():return {"ok":False,"error":"target is not a readable file"}

    if cmd in ("/*.dex","/*.class","/*.jar","/*.apk","/*.aab","/*.wasm","/*.db","/*.sqlite","/*.sqlite3","/*.json","/*.pb","/*.protobuf","/*.pak","/*.img","/*.iso"):
        return {"ok":True,"module":mod,"format":extended_summary(p),"evidence":extract(p)}
    if cmd in ("/*.exe","/*.dll","/*.so","/*.elf","/*.dat","/*.bin"):
        return {"ok":True,"module":mod,"native":native_summary(p),"evidence":extract(p)}
    if cmd in ("/py","/*.py"):
        return {"ok":True,"module":mod,"format":detect_format(p),"python":python_summary(p),"evidence":extract(p)}
    if cmd in ("/**.***","/convertany","/anyformat"):
        return {"ok":True,"module":mod,"format":detect_format(p),"conversion":conversion_plan(p,arg or "evidence360"),"tools":available_tools(),"evidence":extract(p)}

    # OCR/readiness routes are explicit and never overwrite the selected input.
    if cmd=="/ocrreadiness":return {"ok":True,"module":mod,"readiness":ocr_readiness(p),"capabilities":ocr_capabilities()}
    if cmd in ("/pdfocr","/ocrpdf","/ocrscan"):
        if not arg:return {"ok":False,"error":"OCR output folder required in arg","readiness":ocr_readiness(p)}
        return {"ok":True,"module":mod,"ocr":ocr_pages(p,arg)}
    if cmd=="/searchablepdf":
        if not arg:return {"ok":False,"error":"new output PDF path required in arg"}
        if Path(arg).resolve()==p.resolve():return {"ok":False,"error":"searchable PDF output must not overwrite input"}
        return searchable_pdf(p,arg)

    # HTML conversion requires an explicit output path.
    if cmd in ("/office2html","/document2html","/word2html","/docx2html","/excel2html","/xlsx2html","/csv2html","/pdf2html"):
        if not arg:return {"ok":False,"error":"HTML output path required in arg"}
        return html_convert(p,arg)
    if cmd in ("/pdfrichhtml","/pdfocrhtml"):
        if not arg:return {"ok":False,"error":"HTML output path required in arg"}
        return pdf_rich(p,arg,ocr=(cmd=="/pdfocrhtml"))

    # Execute office conversion only when a destination is explicit.
    if cmd in ("/officeconvert","/officeengine","/csv2xlsx","/xlsx2csv"):
        if not arg:return {"ok":False,"error":"destination path required in arg"}
        return office_convert(p,arg)

    doc_targets={"/pdf2word":"docx","/pdf2docx":"docx","/pdf2excel":"xlsx","/pdf2xlsx":"xlsx","/word2pdf":"pdf","/docx2pdf":"pdf","/excel2pdf":"pdf","/xlsx2pdf":"pdf","/word2excel":"xlsx","/excel2word":"docx"}
    if cmd in doc_targets:
        result={"ok":True,"module":mod,"conversion":document_conversion_plan(p,doc_targets[cmd]),"evidence":extract(p,include_numbers=False)}
        # Preserve planning behavior unless caller explicitly supplies a destination.
        if arg:result["execution"]=office_convert(p,arg)
        return result

    if cmd=="/base64":
        r=decode_base64(p.read_text(encoding="utf-8",errors="replace").strip())
        if r.get("ok") and isinstance(r.get("bytes"),bytes):
            b=r.pop("bytes");r.update({"size":len(b),"hex":b.hex(),"text_utf8":b.decode("utf-8","replace")})
        return r
    if cmd=="/base44":return decode_base44(p.read_text(encoding="utf-8",errors="replace").strip())
    if cmd=="/zip":return {"ok":True,"inventory":zip_inventory(p)}
    if cmd=="/rar":return {"ok":True,"inventory":rar_inventory(p)}
    if cmd=="/7zip":return {"ok":True,"inventory":sevenzip_inventory(p)}
    if cmd=="/xml":return {"ok":True,"summary":xml_summary(p)}
    if cmd=="/svg":return {"ok":True,"summary":svg_summary(p)}
    if cmd=="/css":return {"ok":True,"summary":css_tokens(p.read_text(encoding="utf-8",errors="replace"))}
    if cmd=="/blob":return {"ok":True,"summary":blob_summary(p.read_bytes())}
    if cmd=="/chunk":return {"ok":True,"chunks":code_chunks(p.read_bytes(),int(arg or 4096))}
    if cmd in ("/smgrep","/semgrep"):return {"ok":True,"plan":semgrep_plan(p)}
    return {"ok":True,"module":mod,"evidence":extract(p)}

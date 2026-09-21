"""Built-in extractor module catalog for Lola UI/automation.

Adapters describe how evidence sources fit together. Ghidra is for native PE/ELF
static analysis when installed; Frida remains an explicitly authorized attach-only
runtime evidence source and is never required for ordinary extraction.
"""
MODULES=[
 {"id":"allcode","mode":"static","purpose":"Normalize all observable code/string evidence."},
 {"id":"codestring","mode":"static","purpose":"ASCII and conservative UTF-16 string extraction with offsets."},
 {"id":"extractormodule","mode":"static","purpose":"Universal file fingerprint, signatures, regions and evidence."},
 {"id":"extractorrefactoring","mode":"analysis","purpose":"Refactor generated extractor/report code, never the imported binary."},
 {"id":"refactoringcode","mode":"analysis","purpose":"Normalize generated reconstruction scaffolds."},
 {"id":"codeencode","mode":"static","purpose":"Encoding evidence and BOM/string classification."},
 {"id":"codeencoder","mode":"export","purpose":"Encode generated reports/JSON/text; imported target remains unchanged."},
 {"id":"library","mode":"reference","purpose":"Built-in semantic symbol and extractor catalog."},
 {"id":"sources","mode":"provenance","purpose":"Record file/hash/offset/encoding provenance for findings."},
 {"id":"ghidra","mode":"optional-static","purpose":"Native PE/ELF static-analysis adapter when Ghidra is installed."},
 {"id":"frida","mode":"optional-runtime","purpose":"Authorized attach-only runtime evidence adapter; no stealth or target modification."},
 {"id":"js","mode":"static","purpose":"JavaScript marker/source evidence."},
 {"id":"vbscript","mode":"static","purpose":"VB/VBScript marker/source evidence."},
 {"id":"scripts","mode":"static","purpose":"Script-language marker inventory."},
 {"id":"toolsextractor","mode":"reference","purpose":"Inventory available managed/system analysis tools."},
]

ALIASES={
 "/deep-dive":"extractormodule","/allcode":"allcode","/codestring":"codestring",
 "/extractormodule":"extractormodule","/extractorrefactoring":"extractorrefactoring",
 "/refactoringcode":"refactoringcode","/codeencode":"codeencode","/codeencoder":"codeencoder",
 "/library":"library","/sources":"sources","/ghidra":"ghidra","/frida":"frida",
 "/js":"js","/vbscript":"vbscript","/scripts":"scripts","/toolsextractor":"toolsextractor"
}

def catalog():
    return MODULES

def resolve(command):
    mid=ALIASES.get(command.lower())
    return next((m for m in MODULES if m["id"]==mid),None)

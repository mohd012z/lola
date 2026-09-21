"""Built-in extractor module catalog for Lola UI/automation.

Adapters describe how evidence sources fit together. Ghidra is for native PE/ELF
static analysis when installed; Frida remains an explicitly authorized attach-only
runtime evidence source and is never required for ordinary extraction.
"""
MODULES=[
 {"id":"py","mode":"static-source","purpose":"Python AST, imports, classes and function evidence."},
 {"id":"convertany","mode":"convert-plan","purpose":"Auto-detect compatible representation conversion path."},
 {"id":"anyformat","mode":"convert-plan","purpose":"Wildcard format conversion/evidence fallback."},
 {"id":"dex2smali","mode":"convert","purpose":"DEX to Smali representation."},
 {"id":"smali2dex","mode":"convert","purpose":"Smali to DEX representation."},
 {"id":"dex2java","mode":"reconstruct","purpose":"DEX to reconstructed Java source."},
 {"id":"smali2java","mode":"reconstruct","purpose":"Smali to reconstructed Java source."},
 {"id":"androidconvert","mode":"reference","purpose":"Android format conversion matrix."},
 {"id":"dex","mode":"static","purpose":"DEX header/table evidence."},
 {"id":"class","mode":"static","purpose":"Java class header/constant-pool evidence."},
 {"id":"jar","mode":"static","purpose":"JAR package inventory."},
 {"id":"apk","mode":"static","purpose":"APK package inventory."},
 {"id":"aab","mode":"static","purpose":"Android App Bundle inventory."},
 {"id":"wasm","mode":"static","purpose":"WebAssembly header evidence."},
 {"id":"sqlite","mode":"static","purpose":"SQLite read-only schema inventory."},
 {"id":"json","mode":"static","purpose":"JSON structural inventory."},
 {"id":"protobuf","mode":"static","purpose":"Schema-less protobuf wire inventory."},
 {"id":"pak","mode":"static","purpose":"PAK raw-container evidence."},
 {"id":"img","mode":"static","purpose":"IMG raw-container evidence."},
 {"id":"iso","mode":"static","purpose":"ISO raw-container evidence."},
 {"id":"exe","mode":"static-native","purpose":"PE/EXE header and section evidence; target is never loaded."},
 {"id":"so","mode":"static-native","purpose":"ELF/shared-object header and section evidence; target is never loaded."},
 {"id":"dat","mode":"static","purpose":"Generic DAT/raw classification by content, signatures, chunks and strings."},
 {"id":"codecli","mode":"interface","purpose":"CLI entry point for managed extraction modules."},
 {"id":"cpp","mode":"static","purpose":"C++ source/native marker evidence; no target execution."},
 {"id":"c","mode":"static","purpose":"C source/native marker evidence; no target execution."},
 {"id":"vector","mode":"static","purpose":"Vector/container terminology and structured numeric evidence."},
 {"id":"base64","mode":"decode","purpose":"Strict standard Base64 decode of selected text/evidence."},
 {"id":"base44","mode":"reference","purpose":"Unsupported until an explicit documented Base44 codec is registered."},
 {"id":"zip","mode":"archive","purpose":"Bounded ZIP inventory and safe workspace extraction."},
 {"id":"rar","mode":"archive","purpose":"Optional RAR inventory through installed backend; no password guessing."},
 {"id":"7zip","mode":"archive","purpose":"Optional 7z inventory through py7zr; no password guessing."},
 {"id":"semgrep","mode":"optional-static","purpose":"Static source-code rules on user-selected source/workspace."},
 {"id":"blob","mode":"static","purpose":"Raw blob size/header/zero-density evidence."},
 {"id":"chunk","mode":"static","purpose":"Bounded byte-range chunk map with exact offsets."},
 {"id":"svg","mode":"static","purpose":"SVG/XML structure inventory."},
 {"id":"xml","mode":"static","purpose":"XML element/root structure inventory."},
 {"id":"css","mode":"static","purpose":"CSS selector/property token inventory."},
 {"id":"formatcode","mode":"static","purpose":"Auto-route known source/text/archive formats to safe extractors."},
 {"id":"wildcard","mode":"static","purpose":"Fallback any-file fingerprint/blob/chunk extraction."},
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
 "/py":"py","/*.py":"py","/**.***":"anyformat","/convertany":"convertany","/anyformat":"anyformat",
 "/dex2smali":"dex2smali","/smali2dex":"smali2dex","/dex2java":"dex2java","/smali2java":"smali2java","/androidconvert":"androidconvert",
 "/*.dex":"dex","/*.class":"class","/*.jar":"jar","/*.apk":"apk","/*.aab":"aab","/*.wasm":"wasm",
 "/*.db":"sqlite","/*.sqlite":"sqlite","/*.sqlite3":"sqlite","/*.json":"json","/*.pb":"protobuf","/*.protobuf":"protobuf",
 "/*.pak":"pak","/*.img":"img","/*.iso":"iso",
 "/*.exe":"exe","/*.dll":"exe","/*.so":"so","/*.elf":"so","/*.dat":"dat","/*.bin":"dat",
 "/codecli":"codecli","/c++":"cpp","/cpp":"cpp","/c":"c","/vector":"vector",
 "/base64":"base64","/base44":"base44","/zip":"zip","/rar":"rar","/7zip":"7zip",
 "/smgrep":"semgrep","/semgrep":"semgrep","/blob":"blob","/chunk":"chunk",
 "/svg":"svg","/xml":"xml","/css":"css","/*formatcode":"formatcode","/*.**":"wildcard","/*.***":"wildcard",
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

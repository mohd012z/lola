#!/usr/bin/env python3
import argparse
import json
import re
from collections import Counter
from pathlib import Path

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_VIEW_LINES_PER_FILE = 1200
MAX_TOTAL_VIEW_CHARS = 3_000_000
MAX_STRINGS = 6000
MAX_ITEMS = 5000

SOURCE_EXTS = {
    ".js",".jsx",".mjs",".cjs",".ts",".tsx",".html",".htm",".vue",".svelte",
    ".json",".yaml",".yml",".xml",".md",".txt",".env",".properties",".toml",
    ".conf",".ini",".sql",".graphql",".gql",".sh",".ps1",".py",".java",".kt",
    ".kts",".swift",".m",".mm",".dart",".go",".php",".rb",".cs",".gradle",
    ".pro",".cfg",".plist",".entitlements"
}

SECRET_NAME_RE = re.compile(r"(?i)(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|bearer|credential)")
ASSIGN_SECRET_RE = re.compile(
    r"""(?ix)
    \b(?P<name>[A-Za-z_][A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|credential)[A-Za-z0-9_.-]*)
    \s*[:=]\s*
    (?P<quote>["'])(?P<value>[^"'\r\n]{1,500})(?P=quote)
    """
)
PROVIDER_TOKEN_RE = re.compile(r"(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]{0,20000}?-----END [A-Z0-9 ]*PRIVATE KEY-----")
URL_RE = re.compile(r"""(?i)\b(?:https?|wss?|ftp|ftps|sftp|ssh|mqtts?|amqps?|grpc|grpcs)://[^\s"'<>]+""")
STRING_RE = re.compile(r"""(?s)(?P<q>["'\x60])(?P<body>(?:\\.|(?!\1).){1,500}?)(?P=q)""")
IMPORT_RE = re.compile(r"""(?m)^\s*(?:import\s+.+?\s+from\s+|import\s*|require\s*\(|from\s+|using\s+|#include\s*[<"])(?P<mod>[^"'<>\s();]+)""")
FUNC_PATTERNS = [
    re.compile(r"""(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\("""),
    re.compile(r"""(?m)^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"""),
    re.compile(r"""(?m)^\s*def\s+(?P<name>[A-Za-z_]\w*)\s*\("""),
    re.compile(r"""(?m)^\s*(?:public|private|protected|static|final|suspend|async|\s)*\s*(?:fun|func)\s+(?P<name>[A-Za-z_]\w*)\s*\("""),
]
CLASS_PATTERNS = [
    re.compile(r"""(?m)^\s*(?:export\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)"""),
    re.compile(r"""(?m)^\s*(?:public\s+|private\s+|internal\s+)?(?:class|struct|enum|interface)\s+(?P<name>[A-Za-z_]\w*)"""),
]

MOD_PATTERNS = {
    "file-write": re.compile(r"(?i)\b(writeFile(?:Sync)?|appendFile(?:Sync)?|createWriteStream|Files\.write|FileOutputStream|writeText|writeBytes)\b"),
    "file-delete": re.compile(r"(?i)\b(unlink(?:Sync)?|rm(?:Sync)?|remove|deleteFile|Files\.delete|File\.delete)\b"),
    "file-move": re.compile(r"(?i)\b(rename(?:Sync)?|move|copyFile|Files\.move|Files\.copy)\b"),
    "storage-write": re.compile(r"(?i)\b(localStorage\.setItem|sessionStorage\.setItem|IndexedDB|put\(|setItem\(|SharedPreferences|UserDefaults)\b"),
    "dom-write": re.compile(r"(?i)\b(innerHTML|outerHTML|insertAdjacentHTML|document\.write|textContent\s*=|setAttribute\()"),
    "database-write": re.compile(r"(?i)\b(INSERT\s+INTO|UPDATE\s+\w+|DELETE\s+FROM|\.update\(|\.delete\(|\.insert\(|\.save\()"),
    "network-mutation": re.compile(r"(?i)\b(fetch|axios\.(post|put|patch|delete)|method\s*:\s*['\"](POST|PUT|PATCH|DELETE)['\"])"),
}

FALLBACK_PATTERNS = {
    "try-catch": re.compile(r"(?i)\btry\b|\bcatch\s*\("),
    "promise-catch": re.compile(r"\.catch\s*\("),
    "fallback-or": re.compile(r"\|\|"),
    "fallback-nullish": re.compile(r"\?\?"),
    "default-value": re.compile(r"(?i)\b(default|fallback)\b"),
    "retry": re.compile(r"(?i)\b(retry|backoff|reconnect|attempts?|maxRetries)\b"),
    "error-handler": re.compile(r"(?i)\b(onerror|errorHandler|handleError|except\b|rescue\b)\b"),
}

CRYPTO_PATTERNS = {
    "encrypt": re.compile(r"(?i)\b(createCipheriv|subtle\.encrypt|Cipher\.getInstance|AES/GCM|encrypt\()"),
    "decrypt": re.compile(r"(?i)\b(createDecipheriv|subtle\.decrypt|decrypt\()"),
    "hash": re.compile(r"(?i)\b(createHash|subtle\.digest|SHA-?256|SHA-?512|MD5|SHA-?1)\b"),
    "kdf": re.compile(r"(?i)\b(PBKDF2|scrypt|argon2|bcrypt|HKDF|deriveKey|deriveBits)\b"),
    "sign": re.compile(r"(?i)\b(createSign|createVerify|subtle\.sign|subtle\.verify|JWT\.sign|JWT\.verify|sign\(|verify\()"),
    "random": re.compile(r"(?i)\b(randomBytes|randomFill|randomUUID|getRandomValues|SecureRandom)\b"),
    "key-store": re.compile(r"(?i)\b(Keychain|Keystore|KeyStore|SecretKey|CryptoKey|privateKey|publicKey|keyAlias)\b"),
}

TRANSPARENT_SOURCES = {
    "environment": re.compile(r"(?i)(process\.env|import\.meta\.env|System\.getenv|os\.environ|Environment\.GetEnvironmentVariable)"),
    "request-input": re.compile(r"(?i)(req\.(query|body|params|headers)|request\.(args|form|json)|location\.(search|hash)|URLSearchParams)"),
    "device": re.compile(r"(?i)(navigator\.|Build\.|UIDevice|Settings\.Secure|AdvertisingId|identifierForVendor)"),
    "storage-read": re.compile(r"(?i)(localStorage\.getItem|sessionStorage\.getItem|readFile|readFileSync|SharedPreferences|getString|UserDefaults)"),
}
TRANSPARENT_SINKS = {
    "network": re.compile(r"(?i)(fetch\(|axios\.|XMLHttpRequest|WebSocket|http\.request|https\.request|send\()"),
    "storage-write": MOD_PATTERNS["storage-write"],
    "filesystem-write": MOD_PATTERNS["file-write"],
    "html": re.compile(r"(?i)(innerHTML|outerHTML|insertAdjacentHTML|document\.write)"),
    "database": re.compile(r"(?i)(\.query\(|\.execute\(|INSERT\s+INTO|UPDATE\s+\w+|DELETE\s+FROM)"),
    "command": re.compile(r"(?i)(child_process\.exec|execSync|Runtime\.getRuntime\(\)\.exec|ProcessBuilder)"),
}

HIDDEN_CODE_RE = re.compile(r"(?i)(display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0|aria-hidden\s*=\s*['\"]true|\.hidden\s*=\s*true|setAttribute\(\s*['\"]hidden)")
ENV_REF_RE = re.compile(r"(?i)(process\.env(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]]+\])|import\.meta\.env\.[A-Za-z_][A-Za-z0-9_]*|System\.getenv\([^)]+\)|os\.environ(?:\[[^\]]+\]|\.get\([^)]+\)))")
ROUTE_RE = re.compile(r"""(?i)\b(?:app|router|server)\.(get|post|put|patch|delete|options|head|use)\s*\(\s*["']([^"']+)["']""")

def line_no(text, pos):
    return text.count("\n", 0, pos) + 1

def mask_value(value):
    if not value:
        return "<redacted>"
    n = len(value)
    if n <= 4:
        return "<redacted>"
    return value[:2] + ("*" * min(max(n - 4, 4), 16)) + value[-2:] + f" ({n} chars)"

def redact_text(text):
    text = PRIVATE_KEY_RE.sub("<PRIVATE_KEY_REDACTED>", text)
    text = PROVIDER_TOKEN_RE.sub(lambda m: mask_value(m.group(0)), text)
    def sub_assign(m):
        return f'{m.group("name")}={m.group("quote")}{mask_value(m.group("value"))}{m.group("quote")}'
    return ASSIGN_SECRET_RE.sub(sub_assign, text)

def safe_read(path):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

def add_line_item(bucket, kind, path, line, text, extra=None):
    if len(bucket) >= MAX_ITEMS:
        return
    item = {"kind": kind, "path": str(path), "line": line, "preview": redact_text(text.strip())[:1000]}
    if extra:
        item.update(extra)
    bucket.append(item)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="target-manifest.json")
    ap.add_argument("--urls", default="url-report.json")
    ap.add_argument("--output", default="code-analysis.json")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    try:
        url_data = json.loads(Path(args.urls).read_text(encoding="utf-8-sig"))
    except Exception:
        url_data = {"urls": []}

    files_out = []
    imports, functions, classes, env_refs, routes = [], [], [], [], []
    secret_refs, strings, modifications, fallbacks, crypto, transparent, hidden = [], [], [], [], [], [], []
    ext_counts = Counter()
    total_lines = 0
    total_chars = 0
    total_view_chars = 0

    for mf in manifest.get("files", []):
        path = Path(mf.get("path", ""))
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in SOURCE_EXTS and path.name not in {"Dockerfile","Containerfile","Caddyfile","AndroidManifest.xml","Info.plist"}:
            continue
        text = safe_read(path)
        if text is None:
            files_out.append({
                "path": str(path), "extension": ext, "bytes": mf.get("bytes", 0),
                "lines": None, "truncated": True, "view": "", "note": "Skipped: unreadable or over 2 MB"
            })
            continue

        lines = text.splitlines()
        line_count = len(lines)
        total_lines += line_count
        total_chars += len(text)
        ext_counts[ext or "[none]"] += 1

        view_lines = lines[:MAX_VIEW_LINES_PER_FILE]
        view = redact_text("\n".join(view_lines))
        if total_view_chars + len(view) > MAX_TOTAL_VIEW_CHARS:
            remain = max(0, MAX_TOTAL_VIEW_CHARS - total_view_chars)
            view = view[:remain]
        total_view_chars += len(view)
        files_out.append({
            "path": str(path), "name": path.name, "extension": ext, "bytes": mf.get("bytes", len(text)),
            "lines": line_count, "truncated": line_count > MAX_VIEW_LINES_PER_FILE or len(view) < len("\n".join(view_lines)),
            "view": view
        })

        for m in IMPORT_RE.finditer(text):
            if len(imports) < MAX_ITEMS:
                imports.append({"path": str(path), "line": line_no(text,m.start()), "module": m.group("mod")[:300]})
        for pat in FUNC_PATTERNS:
            for m in pat.finditer(text):
                if len(functions) < MAX_ITEMS:
                    functions.append({"path": str(path), "line": line_no(text,m.start()), "name": m.group("name")})
        for pat in CLASS_PATTERNS:
            for m in pat.finditer(text):
                if len(classes) < MAX_ITEMS:
                    classes.append({"path": str(path), "line": line_no(text,m.start()), "name": m.group("name")})
        for m in ENV_REF_RE.finditer(text):
            add_line_item(env_refs, "environment", path, line_no(text,m.start()), m.group(0))
        for m in ROUTE_RE.finditer(text):
            if len(routes) < MAX_ITEMS:
                routes.append({"path": str(path), "line": line_no(text,m.start()), "method": m.group(1).upper(), "route": m.group(2)})

        for m in ASSIGN_SECRET_RE.finditer(text):
            if len(secret_refs) < MAX_ITEMS:
                secret_refs.append({
                    "path": str(path), "line": line_no(text,m.start()), "type": "named-secret",
                    "name": m.group("name"), "masked": mask_value(m.group("value"))
                })
        for m in PROVIDER_TOKEN_RE.finditer(text):
            if len(secret_refs) < MAX_ITEMS:
                secret_refs.append({
                    "path": str(path), "line": line_no(text,m.start()), "type": "provider-token",
                    "name": "provider token", "masked": mask_value(m.group(0))
                })
        for m in PRIVATE_KEY_RE.finditer(text):
            if len(secret_refs) < MAX_ITEMS:
                secret_refs.append({
                    "path": str(path), "line": line_no(text,m.start()), "type": "private-key",
                    "name": "private key block", "masked": "<PRIVATE_KEY_REDACTED>"
                })
        for i, line in enumerate(lines, 1):
            sm = SECRET_NAME_RE.search(line)
            if sm and len(secret_refs) < MAX_ITEMS:
                if not any(x["path"] == str(path) and x["line"] == i for x in secret_refs[-20:]):
                    secret_refs.append({
                        "path": str(path), "line": i, "type": "secret-reference",
                        "name": sm.group(0), "masked": "<value not collected>"
                    })

        for m in STRING_RE.finditer(text):
            if len(strings) >= MAX_STRINGS:
                break
            body = m.group("body")
            if len(body.strip()) < 2:
                continue
            sensitive = bool(SECRET_NAME_RE.search(text[max(0,m.start()-80):m.start()+20]) or PROVIDER_TOKEN_RE.search(body))
            value = "<REDACTED_SECRET_STRING>" if sensitive else redact_text(body[:500])
            strings.append({"path":str(path),"line":line_no(text,m.start()),"value":value,"sensitive":sensitive})

        for kind,pat in MOD_PATTERNS.items():
            for m in pat.finditer(text):
                ln=line_no(text,m.start()); line=lines[ln-1] if 0<ln<=len(lines) else m.group(0)
                add_line_item(modifications, kind, path, ln, line)

        for kind,pat in FALLBACK_PATTERNS.items():
            for m in pat.finditer(text):
                ln=line_no(text,m.start()); line=lines[ln-1] if 0<ln<=len(lines) else m.group(0)
                add_line_item(fallbacks, kind, path, ln, line)

        for kind,pat in CRYPTO_PATTERNS.items():
            for m in pat.finditer(text):
                ln=line_no(text,m.start()); line=lines[ln-1] if 0<ln<=len(lines) else m.group(0)
                add_line_item(crypto, kind, path, ln, line, {"passwordOrKeyRelated": bool(SECRET_NAME_RE.search(line))})

        src_hits=[]
        sink_hits=[]
        for kind,pat in TRANSPARENT_SOURCES.items():
            for m in pat.finditer(text):
                src_hits.append((line_no(text,m.start()),kind,m.group(0)[:120]))
        for kind,pat in TRANSPARENT_SINKS.items():
            for m in pat.finditer(text):
                sink_hits.append((line_no(text,m.start()),kind,m.group(0)[:120]))
        if src_hits or sink_hits:
            if len(transparent) < MAX_ITEMS:
                transparent.append({
                    "path":str(path),
                    "sources":[{"line":a,"type":b,"preview":c} for a,b,c in src_hits[:100]],
                    "sinks":[{"line":a,"type":b,"preview":c} for a,b,c in sink_hits[:100]],
                    "sourceTypes":sorted({b for _,b,_ in src_hits}),
                    "sinkTypes":sorted({b for _,b,_ in sink_hits})
                })

        for m in HIDDEN_CODE_RE.finditer(text):
            ln=line_no(text,m.start()); line=lines[ln-1] if 0<ln<=len(lines) else m.group(0)
            add_line_item(hidden, "hidden-ui", path, ln, line)

    url_refs=[]
    for u in url_data.get("urls",[]):
        url_refs.append({
            "sourceUrl":u.get("sourceUrl",""),"finalUrl":u.get("finalUrl",""),
            "host":u.get("host",""),"scheme":u.get("scheme",""),
            "status":u.get("status"),"destinationClass":u.get("destinationClass",""),
            "resolvedIps":u.get("resolvedIps",[]),"occurrences":u.get("occurrences",[])
        })

    summary={
        "filesIndexed":len(files_out),"totalLines":total_lines,"totalChars":total_chars,
        "extensions":dict(ext_counts),"imports":len(imports),"functions":len(functions),
        "classes":len(classes),"envRefs":len(env_refs),"routes":len(routes),
        "secretRefs":len(secret_refs),"strings":len(strings),"modifications":len(modifications),
        "fallbacks":len(fallbacks),"cryptoRefs":len(crypto),"transparentFiles":len(transparent),
        "hiddenCodeRefs":len(hidden),"urlRefs":len(url_refs),"codeViewBytes":total_view_chars
    }

    out={
        "summary":summary,
        "extraction":{"imports":imports,"functions":functions,"classes":classes,"environment":env_refs,"routes":routes},
        "codesummary":{"summary":summary,"largestFiles":sorted(
            [{"path":x["path"],"bytes":x.get("bytes",0),"lines":x.get("lines")} for x in files_out],
            key=lambda x:x.get("bytes") or 0, reverse=True)[:100]},
        "codeview":{"files":files_out,"redacted":True,"maxLinesPerFile":MAX_VIEW_LINES_PER_FILE,"maxEmbeddedChars":MAX_TOTAL_VIEW_CHARS},
        "codepassword":{"items":secret_refs,"redacted":True,"note":"Secret values are never stored unmasked in code-analysis.json."},
        "codestring":{"items":strings,"redactedSecrets":True},
        "codetransparent":{"files":transparent,"note":"Source/sink inventory is heuristic; Semgrep taint findings provide stronger evidence where available."},
        "codemodification":{"items":modifications},
        "codefallback":{"items":fallbacks},
        "codeurls":{"items":url_refs},
        "codeencryption":{"items":crypto,"secretValuesCollected":False},
        "hiddenmode":{"items":hidden}
    }
    Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Code analysis written: {Path(args.output).resolve()}")

if __name__=="__main__":
    main()

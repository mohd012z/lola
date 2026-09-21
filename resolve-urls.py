#!/usr/bin/env python3
import argparse
import ipaddress
import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

URL_RE = re.compile(r"""https?://[^\s"'<>\]\[{}]+""", re.I)
TRIM = ".,;:!?)]}'\""

def line_for(text, pos):
    return text.count("\n", 0, pos) + 1

def clean_url(value):
    return value.rstrip(TRIM)

def resolve_host(host):
    if not host:
        return [], "missing-host"
    h = host.strip("[]").lower()
    if h in {"localhost", "localhost.localdomain"} or h.endswith(".localhost"):
        return [], "local-hostname"
    try:
        ips = []
        for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP):
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
        return ips, ""
    except Exception as e:
        return [], f"dns-error: {e}"

def classify_ips(ips):
    if not ips:
        return "unresolved"
    labels = []
    for raw in ips:
        try:
            ip = ipaddress.ip_address(raw.split("%", 1)[0])
            if ip.is_loopback:
                labels.append("loopback")
            elif ip.is_private:
                labels.append("private")
            elif ip.is_link_local:
                labels.append("link-local")
            elif ip.is_multicast:
                labels.append("multicast")
            elif ip.is_reserved:
                labels.append("reserved")
            elif ip.is_unspecified:
                labels.append("unspecified")
            elif ip.is_global:
                labels.append("public")
            else:
                labels.append("non-public")
        except Exception:
            labels.append("unknown")
    return "public" if labels and all(x == "public" for x in labels) else "+".join(sorted(set(labels)))

def public_destination(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in {"http", "https"}:
        return False, [], "unsupported-scheme"
    ips, err = resolve_host(p.hostname or "")
    cls = classify_ips(ips)
    return cls == "public", ips, err or cls

class TrackingRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.chain = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.chain.append({"status": code, "from": req.full_url, "to": newurl})
        ok, _, reason = public_destination(newurl)
        if not ok:
            raise urllib.error.URLError(f"redirect-blocked:{reason}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def probe(url, timeout=6):
    ok, ips, reason = public_destination(url)
    result = {
        "probed": False,
        "status": None,
        "finalUrl": "",
        "redirects": [],
        "resolvedIps": ips,
        "destinationClass": classify_ips(ips),
        "error": "",
        "tls": {},
    }
    if not ok:
        result["error"] = f"probe-blocked:{reason}"
        return result

    redirect = TrackingRedirect()
    opener = urllib.request.build_opener(redirect)
    headers = {"User-Agent": "LolaSecurityURLResolver/1.0", "Accept": "*/*"}

    def run(method):
        req = urllib.request.Request(url, headers=headers, method=method)
        return opener.open(req, timeout=timeout)

    response = None
    try:
        try:
            response = run("HEAD")
        except urllib.error.HTTPError as e:
            if e.code in {400, 403, 405, 501}:
                response = run("GET")
            else:
                raise
        result["probed"] = True
        result["status"] = getattr(response, "status", None) or response.getcode()
        result["finalUrl"] = response.geturl()
        result["redirects"] = redirect.chain
    except urllib.error.HTTPError as e:
        result["probed"] = True
        result["status"] = e.code
        result["finalUrl"] = e.geturl() or url
        result["redirects"] = redirect.chain
        result["error"] = f"http-error:{e.code}"
    except Exception as e:
        result["redirects"] = redirect.chain
        result["error"] = str(e)
    finally:
        try:
            if response:
                response.close()
        except Exception:
            pass

    final = result["finalUrl"] or url
    p = urllib.parse.urlsplit(final)
    if p.scheme == "https" and p.hostname and result["destinationClass"] == "public":
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((p.hostname, p.port or 443), timeout=timeout) as raw:
                with ctx.wrap_socket(raw, server_hostname=p.hostname) as tls:
                    cert = tls.getpeercert()
                    result["tls"] = {
                        "version": tls.version() or "",
                        "cipher": (tls.cipher() or ("", "", ""))[0],
                        "subject": cert.get("subject", []),
                        "issuer": cert.get("issuer", []),
                        "notBefore": cert.get("notBefore", ""),
                        "notAfter": cert.get("notAfter", ""),
                    }
        except Exception as e:
            result["tls"] = {"error": str(e)}
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="target-manifest.json")
    ap.add_argument("--output", default="url-report.json")
    ap.add_argument("--probe", action="store_true", help="Resolve public destinations and follow redirects")
    ap.add_argument("--timeout", type=int, default=6)
    ap.add_argument("--max-probe", type=int, default=100)
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    occurrences = defaultdict(list)

    for item in manifest.get("files", []):
        path = Path(item.get("path", ""))
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > 5 * 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in URL_RE.finditer(text):
            url = clean_url(m.group(0))
            if url:
                occurrences[url].append({"path": str(path), "line": line_for(text, m.start())})

    rows = []
    for idx, (url, refs) in enumerate(sorted(occurrences.items())):
        p = urllib.parse.urlsplit(url)
        ips, dns_error = resolve_host(p.hostname or "")
        cls = classify_ips(ips)
        row = {
            "sourceUrl": url,
            "scheme": p.scheme,
            "host": p.hostname or "",
            "port": p.port,
            "path": p.path or "/",
            "queryPresent": bool(p.query),
            "occurrences": refs,
            "resolvedIps": ips,
            "destinationClass": cls,
            "dnsError": dns_error,
            "probed": False,
            "status": None,
            "finalUrl": "",
            "redirects": [],
            "tls": {},
            "error": "",
        }
        if args.probe and idx < args.max_probe:
            live = probe(url, timeout=args.timeout)
            row.update(live)
        elif args.probe and idx >= args.max_probe:
            row["error"] = f"probe-limit:{args.max_probe}"
        rows.append(row)

    out = {
        "target": manifest.get("target", ""),
        "probeEnabled": bool(args.probe),
        "urlCount": len(rows),
        "publicCount": sum(1 for x in rows if x["destinationClass"] == "public"),
        "nonPublicCount": sum(1 for x in rows if x["destinationClass"] != "public"),
        "urls": rows,
    }
    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"URL inventory written: {Path(args.output).resolve()}")
    if args.probe:
        print(f"Live public URL probing enabled; max {args.max_probe} URLs.")

if __name__ == "__main__":
    main()

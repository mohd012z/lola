# Lola - Codex Security Scanner

Custom Semgrep rules plus automatic target discovery and a self-contained visual HTML report.

## Fastest Windows usage

~~~powershell
python -m pip install semgrep
.\scan-security.ps1 "C:\Projects\my-app"
~~~

After the scan, two outputs are created:

~~~text
semgrep-results.json   raw machine-readable results
semgrep-report.html    visual interactive dashboard
~~~

The HTML report opens automatically. Use `-NoOpen` if you only want it generated:

~~~powershell
.\scan-security.ps1 "C:\Projects\my-app" -NoOpen
~~~

## Visual report

The dashboard shows:
- total findings
- ERROR / WARNING / INFO cards
- number of affected files
- top triggered rules
- search
- severity filter
- category filter
- rule filter
- file and line number
- CWE/category/confidence metadata
- expandable source snippet when Semgrep provides one

It is self-contained and needs no web/CDN connection.

## What is the target?

The target is the source-code file or folder Semgrep inspects.

Good targets:
- complete source repository
- `src`, `app`, `server`, `public`, or `www`
- individual `.js`, `.ts`, `.html`, `.json`, `.yaml`, `.env`, Vue/Svelte/config files

Usually do not target binaries directly:
- APK/AAB/IPA
- EXE/DLL/JAR
- ZIP/7z/RAR
- PDF/images/video/audio
- generated build output
- `node_modules`

For APK/ZIP analysis, obtain the original or unpacked source tree first.

## Examples

Current folder:

~~~powershell
.\scan-security.ps1 .
~~~

One project:

~~~powershell
.\scan-security.ps1 "C:\Projects\NovaStream"
~~~

One file:

~~~powershell
.\scan-security.ps1 "C:\Projects\NovaStream\src\app.js"
~~~

Strict/CI mode:

~~~powershell
.\scan-security.ps1 "C:\Projects\NovaStream" -Strict
~~~

Rebuild only the visual report from an existing JSON result:

~~~powershell
python build-report.py --input semgrep-results.json --output semgrep-report.html --target "C:\Projects\NovaStream"
~~~

## Coverage

Inventory: URLs, fetch, Axios, XHR, WebSocket, EventSource, environment/config reads, Express-style routes, browser storage writes.

Audit: XSS/HTML sinks, eval/Function, string timers, possible secrets/private keys, wildcard postMessage/CORS, disabled TLS validation, weak hashes, Web Storage credentials, cookie options, shell execution, unsafe deserialization.

Taint rules: selected untrusted browser/request inputs flowing into HTML sinks, redirects, outbound requests (SSRF risk), and shell execution.

A finding is a review signal, not proof of exploitability. A clean scan is also not proof that an application has no vulnerabilities.

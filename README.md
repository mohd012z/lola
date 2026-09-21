# Lola - Codex Security Scanner

This repository contains a custom Semgrep rule pack for discovering an application's exposed surface and auditing common JavaScript/TypeScript/web security mistakes.

## What is the target?

The target is the source-code file or folder that Semgrep inspects.

Use as a target:
- a complete source repository
- a folder such as src, app, server, public, or www
- one source file such as app.js, server.ts, or index.html
- configuration/source files such as JSON, YAML, .env, XML, Vue, Svelte, Dockerfile, or nginx.conf

Do not normally use as a target:
- APK/AAB/IPA
- EXE/DLL/JAR
- ZIP/7z/RAR
- PDF/images/video/audio
- generated build output
- dependency folders such as node_modules

For an APK or ZIP, obtain the original/unpacked source tree first, then scan the source.

## Windows target discovery + scan

From the repository folder:

~~~powershell
python -m pip install semgrep
.\scan-security.ps1 "C:\Projects\my-app"
~~~

The script:
1. verifies the target exists
2. lists candidate source/config files
3. groups them by extension
4. shows the first 30 target files
5. runs Semgrep
6. writes semgrep-results.json
7. prints ERROR/WARNING/INFO totals

Scan the current folder:

~~~powershell
.\scan-security.ps1 .
~~~

Scan one file:

~~~powershell
.\scan-security.ps1 "C:\Projects\my-app\src\app.js"
~~~

Strict/CI mode:

~~~powershell
.\scan-security.ps1 "C:\Projects\my-app" -Strict
~~~

Direct Semgrep:

~~~powershell
semgrep scan --config codex-security.yaml C:\Projects\my-app
~~~

## What is inspected?

The inventory rules map URLs, fetch, Axios, XHR, WebSocket, EventSource, environment/config reads, Express-style routes, and browser storage writes.

The audit rules look for HTML/XSS sinks, eval/Function, string timers, possible credentials/private keys, wildcard postMessage/CORS, disabled TLS verification, weak hashes, Web Storage credentials, unsafe cookie usage, shell execution, and unsafe deserialization.

Taint rules additionally track selected untrusted browser/request inputs into HTML sinks, redirects, outbound URLs (SSRF risk), and shell execution.

A finding is a review signal, not proof of exploitability. A clean scan is also not proof that an application has no vulnerabilities.

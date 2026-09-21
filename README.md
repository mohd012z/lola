# Lola - Codex Security Scanner

Custom Semgrep rules with target discovery, deep attack-surface mapping, and a self-contained visual HTML report.

## Quick start

~~~powershell
python -m pip install semgrep
.\scan-security.ps1 "C:\Projects\my-app"
~~~

The scan now creates three evidence files:

~~~text
target-manifest.json    every candidate source/config path + size + modified UTC + SHA-256
semgrep-results.json    raw Semgrep findings
semgrep-report.html     interactive visual dashboard
~~~

The HTML report opens automatically. Add `-NoOpen` to only generate it.

## What the visual report shows

### 1. Every target path
The Target File Manifest section lists candidate files even when they have zero findings:
- full file path
- extension/type
- file size
- SHA-256
- finding count
- modified timestamp (available as metadata)

This helps answer both:
- "Was this file actually part of target discovery?"
- "Did this file produce any security/inventory finding?"

### 2. Filesystem and application paths
The scanner maps:
- fs read/open paths
- fs write/create paths
- delete/move operations
- path.join / path.resolve / path.normalize
- __dirname / __filename / process.cwd()
- Express sendFile/download paths
- static-content directories
- upload destinations
- file:// URIs
- content:// URIs
- common Windows absolute paths
- common Unix/Android absolute paths

It also has a taint rule for request-controlled data reaching filesystem paths (path traversal review).

### 3. HTTP/API routes and navigation
The scanner maps:
- Express/router GET/POST/PUT/PATCH/DELETE/etc routes
- redirects
- browser location.href / assign / replace
- fetch/Axios/XHR
- WebSocket
- EventSource/SSE
- URLs including cleartext http:// references

### 4. IP and "real client IP" handling
The report identifies code/config that handles:
- IPv4 literals
- IPv6-style literals
- private/loopback IPv4 ranges
- req.ip / req.ips
- socket.remoteAddress
- X-Forwarded-For
- X-Real-IP
- CF-Connecting-IP
- True-Client-IP
- Forwarded
- Fastly-Client-IP
- X-Client-IP
- Express trust proxy
- listeners bound to 0.0.0.0
- DNS resolution
- network listen/bind/connect calls

Important: this maps how the application handles IP information. It does not independently discover a person's physical location. Forwarded client-IP headers are trustworthy only when the proxy chain is correctly controlled and configured.

### 5. Encryption / cryptography
The scanner maps:
- createCipheriv / createDecipheriv
- Web Crypto encrypt/decrypt/digest/sign/verify
- PBKDF2
- scrypt
- HKDF
- crypto.randomBytes/randomFill/randomUUID
- browser getRandomValues
- signing/verification
- JWT sign/verify
- HTTPS/TLS configuration
- algorithm references such as AES-GCM, RSA-OAEP, ChaCha20-Poly1305, bcrypt and Argon2

It also reviews:
- deprecated createCipher/createDecipher
- ECB mode
- static/all-zero IV patterns
- disabled TLS verification
- MD5/SHA-1 and other legacy crypto references

### 6. Database/storage
The scanner inventories:
- database clients/pools/connections
- Mongo/Mongoose-style connection calls
- Sequelize/Prisma-style clients
- query/execute/exec/raw operations
- SQL interpolation/concatenation audit rules

## Attack-surface filters

The visual report can filter by:
- severity
- surface
- category
- file
- rule
- free-text search

Common surfaces include:

~~~text
filesystem
http-files
uploads
http-routes
browser-navigation
network-addresses
private-network
client-ip
proxy-trust
listeners
dns
cleartext-http
encryption
webcrypto
key-derivation
random
signatures
tls
crypto-reference
database
secrets
security
~~~

## Target discovery coverage

Candidate discovery includes JavaScript/TypeScript/HTML plus common configuration and backend/security files such as:

~~~text
.js .jsx .mjs .cjs .ts .tsx .html .vue .svelte
.json .yaml .yml .xml .env .properties .toml
.conf .ini .sql .graphql .gql
.pem .key .crt .cer
.sh .ps1 .py .java .kt .go .php .rb .cs
.gradle .cfg
AndroidManifest.xml
Dockerfile / Containerfile / Caddyfile
nginx.conf / httpd.conf
~~~

Deep AST/taint coverage is strongest for JavaScript/TypeScript. Generic URL/IP/path/secret/crypto-reference rules provide additional cross-language visibility.

## Examples

Scan a complete project:

~~~powershell
.\scan-security.ps1 "C:\Projects\NovaStream"
~~~

Scan one folder:

~~~powershell
.\scan-security.ps1 "C:\Projects\NovaStream\src"
~~~

Scan one file:

~~~powershell
.\scan-security.ps1 "C:\Projects\NovaStream\src\app.js"
~~~

Strict/CI mode:

~~~powershell
.\scan-security.ps1 "C:\Projects\NovaStream" -Strict
~~~

Rebuild the visual report from existing output:

~~~powershell
python build-report.py --input semgrep-results.json --manifest target-manifest.json --output semgrep-report.html --target "C:\Projects\NovaStream"
~~~

Static analysis findings are review signals, not automatic proof that a vulnerability is exploitable. A clean scan is not proof of complete security.

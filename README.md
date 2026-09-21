# Lola - Codex Security Scanner

Custom Semgrep rules with target discovery, deep attack-surface mapping, and a self-contained visual HTML report.

## Quick start

~~~powershell
python -m pip install semgrep
.\scan-security.ps1 "C:\Projects\my-app"
~~~

The scan now creates four evidence files:

~~~text
target-manifest.json    every candidate source/config path + size + modified UTC + SHA-256
url-report.json         source URLs, hosts, DNS/IP classification, optional live final URLs
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

## Device analysis

There are two device layers.

### Static device-surface scan

The Semgrep rules identify where application code accesses or requests:

- browser/OS hints: userAgent, platform, languages
- hardware hints: logical processor count, device memory hint, touch points
- screen size, available screen area, color depth and device-pixel ratio
- high-entropy User-Agent Client Hints
- camera/microphone/media-device APIs
- geolocation APIs
- permission-state APIs
- clipboard
- battery
- browser network information
- storage quota/persistence
- WebRTC/network-candidate surfaces
- Node/Electron host information and network interfaces
- Android Build fields
- Android stable-ID APIs such as ANDROID_ID / IMEI-style references
- Android Wi-Fi/network APIs
- Android sensitive permissions
- iOS UIDevice characteristics
- iOS identifierForVendor / advertising-ID references
- iOS privacy usage-description keys
- Capacitor/Cordova device plugins
- React Native device/privacy packages
- Flutter device/privacy packages

The visual HTML report contains a dedicated **Device & Privacy Map** so these can be filtered separately.

It also maps camera/gallery/files, contacts/calendar, notification, biometric, and account/authentication surfaces:
- browser camera/microphone and file pickers
- WebAuthn / browser Credential Management
- OAuth/OIDC/PKCE references
- Android AccountManager / CredentialManager / Google Sign-In / Firebase Auth
- iOS Sign in with Apple / AuthenticationServices / Keychain
- Android/iOS camera and photo APIs
- contacts/calendar APIs and permissions
- biometric APIs
- push/notification permission APIs
- possible confidential OAuth client secrets embedded in source

The scanner reports where those APIs appear; it does not extract real passwords or enumerate a user's personal account list.

### Actual runtime device snapshot

The repository also contains:

~~~text
device-check.html
~~~

For best browser support, serve the repository locally:

~~~powershell
python -m http.server 8080
~~~

Then open:

~~~text
http://localhost:8080/device-check.html
~~~

The page displays the actual runtime values the browser is allowed to expose, including:

- browser and platform hints
- User-Agent Client Hints where available
- logical processor count
- device-memory hint where supported
- touch capability
- screen dimensions and pixel ratio
- timezone / locale
- network effective type, downlink and RTT where supported
- storage estimate
- battery state where supported
- permission states
- availability of geolocation, media devices, Bluetooth, USB, Serial, HID, NFC, WebAuthn, Web Crypto, WebRTC and related APIs

It performs **no external network request**. You can copy or save the snapshot as JSON.

The page also has explicit user-triggered tests for:
- camera preview
- microphone permission
- photo/file picker
- notification permission
- WebAuthn/passkey platform-authenticator availability
- geolocation permission

Camera and microphone streams only start after the matching button is pressed and have Stop buttons.

It intentionally does not attempt to obtain protected hardware identifiers such as IMEI, SIM identifiers, hardware serial, Android ID, advertising ID, or MAC address. Ordinary browsers also do not expose a complete network-interface list or guaranteed public IP.

## Real / final URL tracing

Every scan performs a static URL inventory from the discovered source/config files. This records:
- exact source URL
- source file and line
- scheme, host, port and path
- DNS-resolved IP addresses when available
- public vs private/loopback/link-local/reserved classification

To verify the real public destination and redirects:

~~~powershell
.\scan-security.ps1 "C:\Projects\NovaStream" -ResolveUrls
~~~

For public HTTP/HTTPS URLs, live verification adds:
- HTTP status
- final URL after redirects
- complete redirect chain
- resolved IP address(es)
- TLS version
- TLS cipher

The resolver deliberately refuses live requests to localhost, private IP ranges, link-local, multicast, reserved and other non-public destinations. Those remain visible in inventory but are not probed.

A URL can be dynamic (for example, assembled from environment variables or runtime data). Static analysis can show the construction site, but a final runtime URL may only be knowable when the application executes.

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
python build-report.py --input semgrep-results.json --manifest target-manifest.json --urls url-report.json --output semgrep-report.html --target "C:\Projects\NovaStream"
~~~

Static analysis findings are review signals, not automatic proof that a vulnerability is exploitable. A clean scan is not proof of complete security.


## Scan modes / command views

The visual report and scanner now support four scan modes:

### /stepview
Shows the scan as **Before → During → After**.

Before includes target selection, candidate file discovery, hidden/sensitive-path discovery and static URL inventory.

During includes Semgrep finding counts, severity totals, protocol surfaces and whether live public URL verification was enabled.

After includes affected-file counts, categories/surfaces and generated evidence outputs.

Run directly:

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode /stepview
~~~

### /protocol
Deep protocol view for HTTP/HTTPS, WS/WSS, DNS, TLS, raw TCP/UDP, SSH/SFTP, FTP, SMTP/IMAP/POP3, MQTT/AMQP, gRPC/protobuf and GraphQL references.

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode /protocol
~~~

The misspelling `/protocal` is also accepted as an alias.

### /hidden
Shows hidden/sensitive surfaces:
- Windows Hidden file attribute
- dot paths/dotfiles
- .env and related config
- key/certificate/keystore references
- hidden HTML/DOM/CSS such as hidden, aria-hidden, display:none, visibility:hidden
- Semgrep hidden-surface findings

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode /hidden
~~~

### /360
Full-surface overview combining:
- files and paths
- URLs and redirects
- IP/network
- device/privacy/accounts
- permissions/camera/media
- encryption/TLS
- protocols
- hidden surfaces
- database/routes
- security findings

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode /360 -ResolveUrls
~~~

After the HTML report opens, the command buttons can switch between `/stepview`, `/protocol`, `/hidden`, and `/360` without rerunning the scan.

An additional generated evidence file is:

~~~text
scan-modes.json
~~~

It contains the structured data behind these four views.


## Deep output modes

### /deep-dive — All Details
This is the main view to use when you want to inspect **everything detected**.

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode /deep-dive -ResolveUrls
~~~

Open `semgrep-report.html` and select **/deep-dive · All Details**.

It shows:
- every detection
- severity
- rule ID
- surface/category
- exact file
- line/column and end location when available
- confidence metadata
- CWE metadata when defined
- detection message
- source snippet when Semgrep provides one
- counts by rule, surface and affected file

`/deepdive` is accepted as an alias.

### /securitycheck
Groups detections into security-control areas instead of showing one long raw list:

- Secrets & credentials
- Injection / execution
- Transport / TLS
- Authentication & session
- Filesystem & path handling
- Network exposure
- Cryptography
- Privacy & device
- Browser messaging / CORS

Each group is marked **Priority review**, **Review**, or **No detection**, with counts and a review action.

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode /securitycheck
~~~

Important: **No detection does not mean secure**. It only means the current custom rules did not flag that control group.

### /anonymus and /anonymous
These aliases open the privacy/identity-exposure audit.

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode /anonymus -ResolveUrls
~~~

It detects or groups:
- public-IP discovery services
- analytics and telemetry SDKs/endpoints
- cookies and persistent browser identifiers
- device/user/client/visitor IDs stored in Web Storage
- fingerprinting libraries
- canvas/WebGL fingerprinting surfaces
- WebRTC ICE/network candidate handling
- advertising/device identifier references
- account-sign-in linkage
- local/client IP handling
- device identifiers
- telemetry user/device context

This mode is for **privacy exposure auditing**. It does not attempt to hide identity, bypass tracking controls, or evade platform/security systems.

## Which output should I open?

For normal use, open:

~~~text
semgrep-report.html
~~~

Then select the view you need:

~~~text
/deep-dive     Every detection and evidence — best for full detail
/securitycheck Security controls and review priorities
/anonymus      Privacy / identity exposure
/360           Whole application surface summary
/stepview      Before / during / after scan flow
/protocol      Protocol-specific view
/hidden        Hidden files/config/UI surfaces
~~~

Machine-readable outputs remain available for automation:

~~~text
target-manifest.json
url-report.json
semgrep-results.json
scan-modes.json
~~~


## Deep code-analysis commands

A normal scan now also creates:

~~~text
code-analysis.json
~~~

This is generated by `analyze-code.py` and feeds the code-analysis views in `semgrep-report.html`.

### /deep-dive code
Combined code overview. Accepted scanner aliases:
- `/deep-code`
- `/deep-dive-code`
- `"/deep-dive code"`

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode "/deep-dive code" -ResolveUrls
~~~

It combines source structure, secret references, strings, data-flow surfaces, modification points, fallback handling, URLs, crypto, and hidden-code signals.

### /extraction
Extracts structural source information:
- imports/modules
- functions
- classes/interfaces/struct-like declarations
- environment/config reads
- HTTP/router route declarations

### /codesummary
Repository/source summary:
- indexed file count
- total source lines/characters
- extensions
- imports/functions/classes
- environment references
- routes
- secret-reference count
- string count
- code modification points
- fallback/error handling points
- crypto references
- URL references
- largest files

### /codeview
Redacted source browser embedded in the HTML report.

To keep the report usable, source previews are bounded per file and globally. Files over the analyzer size limit are indexed in the manifest but their complete text is not embedded.

Secret-like assignments, provider-token patterns, and private-key material are redacted before they are placed in `code-analysis.json`.

### /codepassword
Locates password/token/key/credential references.

The report shows:
- file
- line
- reference type
- variable/key name when known
- masked value or "value not collected"

It intentionally does **not** expose full credential values.

### /codestring
Indexes string literals for searching application messages, route fragments, configuration values and other static strings.

Strings that appear to contain credentials are replaced with a redaction marker.

### /codetransparent
Heuristic source/sink transparency map.

Sources include:
- environment variables
- HTTP/request-controlled input
- device/browser input
- storage/file reads

Sinks include:
- network requests
- browser/storage writes
- filesystem writes
- HTML insertion
- database calls
- command execution

This view is an inventory. Semgrep taint findings remain the stronger evidence when an actual source-to-sink flow is proven.

### /codemodification
Shows code that changes application or stored state, including:
- file create/write/append
- delete/remove
- rename/move/copy
- local/session storage writes
- DOM writes
- database INSERT/UPDATE/DELETE-style operations
- POST/PUT/PATCH/DELETE network calls

### /codefallback
Shows resilience/fallback logic:
- try/catch
- promise catch
- `||` fallback
- `??` nullish fallback
- default/fallback references
- retry/backoff/reconnect
- error handlers

### /codeurls
Shows URLs linked back to source occurrences plus:
- source URL
- final URL when resolved
- scheme/host
- HTTP status when live verification is enabled
- public/private classification
- resolved IP addresses

### /codeencryption
Shows encryption/security-crypto references:
- encryption/decryption
- hashing
- PBKDF2/scrypt/Argon2/bcrypt/HKDF
- signing/verification
- secure random generation
- key-store/keychain references

It marks lines that are password/key-related but never collects unmasked password/key values.

### /hiddenmode
Deep hidden-code view combining:
- hidden DOM/UI code
- hidden/dot paths
- hidden file attributes
- sensitive config/key/certificate files

This complements the existing `/hidden` security-surface mode.

## Updated generated outputs

~~~text
target-manifest.json   every candidate file/path + metadata/hash
url-report.json        URL/DNS/final-URL/TLS data
code-analysis.json     redacted structural/source analysis
semgrep-results.json   raw Semgrep detections
scan-modes.json        structured security/privacy/mode data
semgrep-report.html    main visual viewer
~~~

For the richest single run:

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode "/deep-dive code" -ResolveUrls
~~~

Then use the command buttons in `semgrep-report.html` to move between code and security views.


## Deep network / live process modes

The scanner now creates:

~~~text
network-analysis.json
scan-events.json
network-monitor.html
~~~

### /deep-dive network
Combined network analysis:

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode "/deep-dive network" -ResolveUrls
~~~

Aliases:
- `/deep-network`
- `/deep-dive-network`
- `"/deep-dive network"`

It combines:
- source file → URL relationships
- DNS host/IP resolution
- redirect chains
- final URLs
- HTTP status
- TLS version/cipher when available
- application routes
- public/non-public IP classification
- network-related Semgrep findings
- public-IP discovery references

### /trace
Application-layer trace:

~~~text
source file
  ↓
source URL
  ↓
host/domain
  ↓
DNS IP
  ↓
HTTP redirects
  ↓
final URL
  ↓
TLS
~~~

This is not raw ICMP traceroute.

### /route
Shows application route declarations and their source locations, plus URL destinations.

### /map
Builds a logical graph of:
- source files
- app routes
- source URLs
- hostnames
- DNS IPs
- redirect URLs
- final URLs

The map is logical, not geographic.

### /visible
Shows what is visible from source and resolution data:
- public hostnames
- resolved public IP addresses
- non-public/private addresses
- network listeners/proxy/IP-related findings

It does not perform an external port scan.

### /realip
Shows:
- public IP addresses resolved for application hosts
- code references to public-IP discovery services
- an optional explicit current-device public-IP check in `network-monitor.html`

A browser cannot reliably determine its own public IP without contacting an external server.

### /cctv — live process monitor
This is a **CCTV-style scan status monitor**, not camera recording.

Run:

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -Mode /cctv -ResolveUrls
~~~

or:

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -LiveMonitor -ResolveUrls
~~~

The scanner starts a localhost-only web server bound to:

~~~text
127.0.0.1:8765
~~~

and opens:

~~~text
network-monitor.html
~~~

The page refreshes `scan-events.json` and `network-analysis.json` during processing.

Feeds include:
- start
- target discovery
- manifest
- URL/DNS map
- code analysis
- Semgrep
- mode analysis
- network analysis
- visual report
- complete

The monitor never activates a camera or microphone.

### Live monitor views

The network monitor has:

~~~text
/normal
/hiddenmode
/anonymus
/trace
/route
/map
/visible
/realip
~~~

`/normal` shows a compact network summary.

`/hiddenmode` focuses on private/local/non-public addresses, proxy trust, client-IP handling, and local-network surfaces.

`/anonymus` focuses on identity/privacy exposure such as client-IP handling, privacy-network findings, public-IP discovery references, device/local-network signals, and related telemetry.

### Generated output set

~~~text
target-manifest.json
url-report.json
code-analysis.json
semgrep-results.json
scan-modes.json
network-analysis.json
scan-events.json
semgrep-report.html
network-monitor.html
~~~


## Before-scan anonymous/privacy preflight

Lola now performs a **preflight analysis before the main Semgrep scan**.

Order:

~~~text
/target
   ↓
target discovery + SHA-256 manifest
   ↓
URL/DNS inventory
   ↓
deep code analysis
   ↓
PRE-SCAN PRIVACY / ANONYMOUS PREFLIGHT
   ↓
Semgrep security scan
   ↓
post-scan modes / network analysis / final HTML
~~~

Generated pre-scan evidence:

~~~text
preflight-analysis.json
~~~

### Pre-scan views

~~~text
/preflight
/viewextraction
/viewurls
/map
/routes
/api
/keys
/hiddentraces
/hidemodes
/hidelog
/ipmirror
/certs
~~~

These are available in both:
- `network-monitor.html` during the scan
- `semgrep-report.html` after the scan

### /viewextraction
Shows imports, functions, classes, environment/config reads and route declarations discovered before Semgrep.

### /viewurls
Shows source URLs, hosts, destination classification, status and final URLs when public resolution is enabled.

### /map
Shows the logical file → route/URL → host → DNS IP graph.

During the pre-scan stage, the live monitor uses the preflight graph. After the main network analysis is ready, the richer network graph is available.

### /routes
Shows application route declarations with source file and line.

### /api
Detects API/client usage references such as:
- `/api`
- fetch
- Axios
- XMLHttpRequest
- WebSocket
- GraphQL/gRPC references
- common API endpoint/base variables

### /keys
Shows password/token/key/credential **references only**.

Values are:
- masked, or
- not collected.

Private-key blocks are never copied into the report.

### /hiddentraces
Detection-only view for hidden/stealth-like code references such as private/incognito/background/hidden UI modes.

It does not enable concealment.

### /hidemodes
Detection-only view for hidden/private/silent mode switches in application code.

### /hidelog
Detection-only view for code that appears to suppress, disable, truncate or clear logging/history.

Lola does **not** use this to erase application, OS, browser, security or audit logs.

### /ipmirror
Mirrors application destination DNS/IP resolution:

~~~text
source URL → host → resolved IP(s) → destination class
~~~

It does not infer a user's physical location.

### /certs
Inventories certificate/key-container files with path, size and SHA-256.

Optional public-certificate copy:

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -CopyPublicCerts
~~~

Copies are stored under:

~~~text
.lola-preflight\certs
~~~

Only public certificate formats are copied by the helper. Private-key containers are never copied.

### Capture all source for local review

Optional:

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -CaptureAllCode
~~~

Lola writes redacted source snapshots under:

~~~text
.lola-preflight\code
~~~

Password/token/key assignments and private-key material are redacted in the generated snapshot.

This is intended for local review of a project you are authorized to inspect.

### Event-log privacy

To avoid keeping the Lola process-event JSON after a non-live scan:

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -NoPersistEvents
~~~

When the live monitor is enabled, the event file must exist temporarily so the browser can display progress.

### Safe cleanup after completion

Use:

~~~powershell
.\scan-security.ps1 "C:\Projects\MyApp" -CaptureAllCode -CleanupLolaTemp
~~~

`-CleanupLolaTemp` removes only Lola-generated temporary items:
- `scan-events.json`
- optional `.lola-preflight\code` redacted source snapshots

It deliberately does **not** delete:
- application logs
- Windows/macOS/Linux system logs
- browser history/logs
- security/antivirus/EDR logs
- audit trails
- server access logs
- target-project logs

There is therefore no destructive `/deletelogs` feature. For privacy, Lola minimizes its own persistent temporary data instead of erasing external evidence.


## APK-focused scanning

Lola now has a dedicated APK pipeline. An `.apk` target is automatically routed away from the generic source scanner and into:

~~~text
scan-apk.ps1
  ↓
analyze-apk.py
  ↓
apk-analysis.json
  ↓
build-apk-report.py
  ↓
apk-report.html
~~~

### Quick APK scan

~~~powershell
.\scan-security.ps1 "C:\Apps\sample.apk"
~~~

or directly:

~~~powershell
.\scan-apk.ps1 "C:\Apps\sample.apk"
~~~

The default view is:

~~~text
/apk360
~~~

### APK report modes

~~~text
/apk360
/apkmanifest
/apkpermissions
/apkcomponents
/apkurls
/apkapi
/apkkeys
/apkcerts
/apknative
/apkwebview
/apkcrypto
/apkfiles
/apkcode
/apkrisk
/apktools
~~~

### /apk360
Combined APK summary:
- APK path
- SHA-256
- package name
- file/ZIP entry count
- minimum SDK
- target SDK
- permissions
- exported Android components
- DEX count
- ABI/native library count
- URLs and API references
- redacted secret references
- WebView references
- crypto references
- review findings

### /apkmanifest
Shows package/SDK/application manifest information.

Lola attempts manifest decoding with locally installed tools in this order:
- Android SDK `apkanalyzer`
- `aapt2` / `aapt` metadata where useful
- APKTool fallback for decoded AndroidManifest.xml

If no decoder is installed, the rest of the ZIP/DEX/string analysis still runs.

### /apkpermissions
Lists Android permissions and highlights permission categories that deserve review, such as:
- camera/microphone
- precise/background location
- SMS/call log
- contacts
- phone-state/phone-number access
- install-package requests
- broad package queries
- broad storage access
- system overlay permission

A permission finding means the APK declares the capability; it does not prove misuse.

### /apkcomponents
Shows:
- activities
- activity aliases
- services
- receivers
- providers
- exported state when the decoded manifest is available

Exported components are review signals, not automatic vulnerabilities.

### /apkurls
Recovers literal URL/protocol strings from:
- DEX printable strings
- text resources
- assets/config
- bundled HTML/JavaScript
- media/config files

The report links each recovered URL to its APK entry and binary/text offset.

### /apkapi
Indexes API/endpoint-style references such as:
- /api
- versioned /vN paths
- auth/login/token
- GraphQL
- OAuth
- config/media/stream/video/playlist paths

### /apkkeys
Finds secret/password/token/key-like references in APK resources and DEX strings.

Lola stores only:
- APK entry
- offset
- reference type/name
- masked value or "value not collected"

Full credentials and private-key material are not written to the report.

### /apkcerts
Shows:
- META-INF signing-related entries
- signer/certificate metadata when `apksigner` or `keytool` is installed

Lola does not copy private keys.

### /apknative
Maps:
- ABI folders
- .so native libraries
- native library sizes

Typical ABI groups such as arm64-v8a, armeabi-v7a, x86, or x86_64 are shown separately when present.

### /apkwebview
Looks for WebView-related code/string references such as:
- WebView
- JavaScript enablement
- JavaScript interfaces
- file/content access
- mixed-content handling
- WebView debugging
- loadUrl/evaluateJavascript

These are review locations; they are not automatically exploitable.

### /apkcrypto
Inventories crypto/key-store references such as:
- AES/GCM/CBC/ECB
- Cipher.getInstance
- PBKDF2
- bcrypt/scrypt/Argon2
- SHA/MD5 references
- RSA
- ChaCha20
- KeyStore/SecretKey

Legacy references such as ECB, MD5, or SHA-1 are surfaced for review.

### /apkfiles
Displays the APK ZIP inventory:
- path
- extension
- uncompressed size
- compressed size
- CRC

It also identifies DEX, assets, signing entries, and native libraries.

### /apkcode
Optional JADX decompilation status.

Run:

~~~powershell
.\scan-apk.ps1 "C:\Apps\sample.apk" -Mode /apkcode -Decompile -KeepDecompiled
~~~

When JADX is installed, decompiled output is placed under:

~~~text
.lola-apk\decompiled
~~~

Use only on APKs you are authorized to inspect. Lola does not attempt to defeat code protection or licensing controls.

To decompile temporarily and remove the generated source afterward:

~~~powershell
.\scan-apk.ps1 "C:\Apps\sample.apk" -Decompile -CleanupLolaApk
~~~

### /apkrisk
Collects review findings including:
- sensitive permissions
- exported components
- debug-build flags when detected
- cleartext-traffic settings
- WebView debugging references
- weak/legacy crypto references
- secret-like references

These are static-analysis review signals, not proof that an APK is malicious or exploitable.

### /apktools
Shows which optional local tools Lola can use:

~~~text
apkanalyzer
aapt2
aapt
apksigner
keytool
jadx
apktool
~~~

Python alone provides:
- APK/ZIP integrity
- SHA-256
- file inventory
- DEX/assets/native-library inventory
- printable-string URL/API detection
- redacted secret-reference detection
- WebView/crypto indicator detection

Android SDK/JADX/APKTool utilities add richer manifest, signing, and code information.

### APK generated outputs

~~~text
apk-analysis.json
apk-report.html
.lola-apk\decompiled     optional temporary/decompiled source
~~~


## Python master target launcher

Use `lola.py` as the single Python master entry point.

### Positional target

~~~powershell
python lola.py "C:\Apps\sample.apk"
~~~

### --target option

~~~powershell
python lola.py --target "C:\Apps\sample.apk"
~~~

For a source/project folder:

~~~powershell
python lola.py --target "C:\Projects\MyApp"
~~~

The launcher automatically detects:

~~~text
.apk file       → APK pipeline
folder/project  → source/security pipeline
other file      → source/security pipeline
~~~

### APK modes from Python master

~~~powershell
python lola.py "C:\Apps\sample.apk" --mode /apk360
python lola.py "C:\Apps\sample.apk" --mode /apkpermissions
python lola.py "C:\Apps\sample.apk" --mode /apkurls
python lola.py "C:\Apps\sample.apk" --mode /apkrisk
~~~

Optional decompilation:

~~~powershell
python lola.py "C:\Apps\sample.apk" --mode /apkcode --decompile --keep-decompiled
~~~

### Project modes from Python master

~~~powershell
python lola.py "C:\Projects\MyApp" --mode /360
python lola.py "C:\Projects\MyApp" --mode /deep-dive --resolve-urls
python lola.py "C:\Projects\MyApp" --mode /anonymus --live-monitor
~~~

### Useful master options

~~~text
--target PATH
--mode MODE
--resolve-urls
--live-monitor
--capture-all-code
--copy-public-certs
--decompile
--keep-decompiled
--cleanup
--no-persist-events
--no-open
~~~

You do not need to edit the Python file each time. Pass the target on the command line so paths with spaces and different APK/project locations are handled safely.


## Button-based desktop UI

You no longer need to type Lola scan commands manually.

Start the desktop control panel with:

~~~powershell
python lola_ui.py
~~~

On Windows, you can also double-click:

~~~text
START_LOLA_UI.bat
~~~

### Main workflow

~~~text
1. Browse APK / File / Folder
2. Choose a mode button
3. Select optional checkboxes
4. Press RUN SCAN
5. Watch Live Log
6. Open the generated report from Outputs
~~~

### UI tabs

~~~text
Quick
APK
Security
Code
Network
Pre-scan
Options
Outputs
Live Log
~~~

### Quick Actions

The Quick tab provides one-click presets for:

~~~text
APK Full Scan
APK Deep + JADX
APK Risk Review
Project Deep Dive
Privacy Audit
Deep Network
Live Monitor
Deep Code
~~~

### APK buttons

~~~text
APK 360
Manifest
Permissions
Components
URLs
API
Keys
Certificates
Native .SO
WebView
Crypto
Files
Code / JADX
Risk Review
Tools
~~~

### Security buttons

~~~text
360 Overview
Deep Dive
Security Check
Privacy / Anonymous
Step View
Protocol
Hidden
~~~

### Code-analysis buttons

~~~text
Deep Code
Extraction
Code Summary
Code View
Password / Key
Strings
Transparent Flow
Modification
Fallback
Code URLs
Encryption
Hidden Mode
~~~

### Network buttons

~~~text
Deep Network
Trace
Route
Map
Visible
Real IP
CCTV Monitor
Normal
~~~

### Pre-scan buttons

~~~text
Preflight
View Extraction
View URLs
Routes
API
Keys
Hidden Traces
Hide Modes
Hide Log Detection
IP Mirror
Certs
~~~

The hidden/log-related buttons are detection views only. They do not enable concealment or erase external logs.

### Options are now checkboxes

~~~text
Resolve public URLs / redirects / TLS
Open live network monitor
Capture redacted source snapshot
Copy public certificates
Decompile APK with JADX
Keep JADX output
Clean Lola temporary data
Do not persist Lola event JSON
Do not auto-open final HTML
~~~

### Output panel

The UI automatically shows which generated files currently exist and provides Open buttons for:

~~~text
apk-report.html
apk-analysis.json
semgrep-report.html
network-monitor.html
semgrep-results.json
code-analysis.json
network-analysis.json
preflight-analysis.json
url-report.json
target-manifest.json
scan-modes.json
~~~

### Live Log

The Live Log tab streams the output of the running Lola process into the UI. It includes:
- start
- target path
- current mode
- analysis progress
- errors/warnings from the scanner
- completion status

You can also:
- Stop a running scan
- Clear the UI log
- Copy the UI log
- Open the output folder

### Target safety

The UI automatically detects whether the selected target is an APK or a source/project target.

APK targets require an APK mode.

Project/source targets require Security, Code, Network, or Pre-scan modes.

This prevents accidental mode mismatches.


## Android / Termux mobile UI

For Android, use the mobile localhost web UI instead of the desktop Tkinter UI.

Start with:

~~~bash
python lola_mobile.py
~~~

or:

~~~bash
bash START_LOLA_ANDROID.sh
~~~

The server binds to:

~~~text
127.0.0.1:8766
~~~

and opens:

~~~text
http://127.0.0.1:8766
~~~

The UI is responsive for Android portrait/landscape and includes:

- Choose APK from Android file picker
- APK 360
- Manifest
- Permissions
- Components
- URLs
- API
- Keys
- Certificates
- Native .SO
- WebView
- Crypto
- Files
- Code/JADX
- Risk Review
- Tools
- Run
- Stop
- Live progress
- Live log
- Open report

The selected APK is uploaded only to Lola's localhost Python server and stored under:

~~~text
.lola-mobile/uploads
~~~

The server is bound to localhost by default, so it is not exposed to the LAN.

### Minimal Termux setup

Install Termux from its maintained F-Droid or GitHub release source. Keep Termux and any Termux plugins from the same source/signing family.

Inside Termux:

~~~bash
pkg update
pkg upgrade
pkg install python git
~~~

Then clone or open the Lola repository and run:

~~~bash
cd lola
bash START_LOLA_ANDROID.sh
~~~

Python alone provides the core APK ZIP/DEX/string/native-library analysis.

### Optional richer APK tooling

Additional local Android/Java tools can improve manifest/signing/decompilation detail when available.

Lola detects these automatically:

~~~text
java
apkanalyzer
aapt2
aapt
apksigner
keytool
jadx
apktool
~~~

Use the **Tools** button in Lola Mobile to see which ones are available on the phone.

### Android limits

The Android version is intentionally APK-focused.

The desktop source/project pipeline currently relies on PowerShell/Semgrep orchestration and is better suited to Windows/Linux desktop.

Large APKs or JADX decompilation may use substantial RAM/CPU. Android may stop long-running background work if Termux is heavily restricted by battery/process management, so keep Termux active during deep scans when possible.

### Android generated files

~~~text
.lola-mobile/uploads
apk-analysis.json
apk-report.html
.lola-apk/decompiled       optional
~~~

Lola Mobile does not need Tkinter.

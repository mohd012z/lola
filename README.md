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

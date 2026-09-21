param(
  [Parameter(Position=0)][string]$Target=".",
  [string]$Config="codex-security.yaml",
  [string]$Report="semgrep-results.json",
  [string]$HtmlReport="semgrep-report.html",
  [string]$Manifest="target-manifest.json",
  [string]$UrlReport="url-report.json",
  [string]$ModeReport="scan-modes.json",
  [string]$CodeReport="code-analysis.json",
  [string]$NetworkReport="network-analysis.json",
  [string]$EventReport="scan-events.json",
  [string]$PreflightReport="preflight-analysis.json",
  [ValidateSet("360","stepview","protocol","protocal","hidden","deep-dive","deepdive","securitycheck","anonymous","anonymus","extraction","codesummary","codeview","codepassword","codestring","codetransparent","codemodification","codefallback","codeurls","codeencryption","hiddenmode","deep-code","deep-dive-code","deep-dive code","deep-network","deep-dive-network","deep-dive network","trace","route","map","visible","realip","cctv","normal","viewextraction","viewurls","routes","api","keys","hiddentraces","hidemodes","hidelog","ipmirror","certs","preflight","cleanup","apk360","apkmanifest","apkpermissions","apkcomponents","apkurls","apkapi","apkkeys","apkcerts","apknative","apkwebview","apkcrypto","apkfiles","apkcode","apkrisk","apktools","/360","/stepview","/protocol","/protocal","/hidden","/deep-dive","/deepdive","/securitycheck","/anonymous","/anonymus","/extraction","/codesummary","/codeview","/codepassword","/codestring","/codetransparent","/codemodification","/codefallback","/codeurls","/codeencryption","/hiddenmode","/deep-code","/deep-dive-code","/deep-dive code","/deep-network","/deep-dive-network","/deep-dive network","/trace","/route","/map","/visible","/realip","/cctv","/normal","/viewextraction","/viewurls","/routes","/api","/keys","/hiddentraces","/hidemodes","/hidelog","/ipmirror","/certs","/preflight","/cleanup","/apk360","/apkmanifest","/apkpermissions","/apkcomponents","/apkurls","/apkapi","/apkkeys","/apkcerts","/apknative","/apkwebview","/apkcrypto","/apkfiles","/apkcode","/apkrisk","/apktools")]
  [string]$Mode="/360",
  [switch]$ResolveUrls,
  [switch]$LiveMonitor,
  [int]$MonitorPort=8765,
  [switch]$CaptureAllCode,
  [switch]$CopyPublicCerts,
  [switch]$CleanupLolaTemp,
  [switch]$NoPersistEvents,
  [switch]$Strict,
  [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$script:ScanEvents = @()
$script:MonitorProcess = $null

function Write-ScanEvent([string]$Stage,[string]$Message,[string]$Level="info",[string]$Status="running") {
  $script:ScanEvents += [PSCustomObject]@{
    time = [DateTime]::UtcNow.ToString("o")
    stage = $Stage
    message = $Message
    level = $Level
  }
  if (-not $NoPersistEvents -or $LiveMonitor) {
    [PSCustomObject]@{
      status = $Status
      currentStage = $Stage
      updatedUtc = [DateTime]::UtcNow.ToString("o")
      events = $script:ScanEvents
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $EventReport -Encoding UTF8
  }
}

function Fail([string]$Message) {
  Write-Host "[ERROR] $Message" -ForegroundColor Red
  exit 1
}

if (-not (Test-Path -LiteralPath $Target)) { Fail "Target does not exist: $Target" }

$TargetPath = (Resolve-Path -LiteralPath $Target).Path
if ((Test-Path -LiteralPath $TargetPath -PathType Leaf) -and ([IO.Path]::GetExtension($TargetPath).ToLowerInvariant() -eq ".apk")) {
  if (-not (Test-Path -LiteralPath "scan-apk.ps1")) { Fail "APK target detected but scan-apk.ps1 is missing." }
  Write-Host "APK target detected — switching to Lola APK pipeline." -ForegroundColor Cyan
  $ApkMode = if ($Mode -like "apk*" -or $Mode -like "/apk*") { $Mode } else { "/apk360" }
  $ApkScanner = Join-Path $PSScriptRoot "scan-apk.ps1"
  $ApkParams = @{ Apk = $TargetPath; Mode = $ApkMode }
  if ($NoOpen) { $ApkParams.NoOpen = $true }
  & $ApkScanner @ApkParams
  exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $Config)) { Fail "Config does not exist: $Config" }

Write-ScanEvent "start" "Scan requested in mode $Mode" "info" "running"

$Semgrep = Get-Command semgrep -ErrorAction SilentlyContinue
if (-not $Semgrep) { Fail "Install Semgrep with: python -m pip install semgrep" }

$ConfigPath = (Resolve-Path -LiteralPath $Config).Path

$Extensions = @(
  ".js",".jsx",".mjs",".cjs",".ts",".tsx",".html",".htm",".vue",".svelte",
  ".json",".yaml",".yml",".xml",".md",".txt",".env",".properties",".toml",
  ".conf",".ini",".sql",".graphql",".gql",".pem",".key",".crt",".cer",
  ".sh",".ps1",".py",".java",".kt",".kts",".swift",".m",".mm",".dart",
  ".go",".php",".rb",".cs",".gradle",".pro",".cfg",".plist",".entitlements"
)
$Names = @(
  "Dockerfile","Containerfile","Caddyfile","nginx.conf","httpd.conf",
  ".env",".env.local",".env.development",".env.production",".env.test",
  "AndroidManifest.xml","Info.plist","Podfile","Gemfile","Runner.entitlements"
)
$SkipDirs = @(
  ".git","node_modules","vendor","dist","build","out",".next",".nuxt",
  "coverage",".cache","tmp",".tmp","generated",".generated","Pods",
  ".gradle",".idea",".vscode"
)

if (Test-Path -LiteralPath $TargetPath -PathType Leaf) {
  $Files = @(Get-Item -LiteralPath $TargetPath)
} else {
  $Files = @(Get-ChildItem -LiteralPath $TargetPath -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
    $segments = $_.FullName -split '[\\/]'
    foreach ($d in $SkipDirs) { if ($segments -contains $d) { return $false } }
    $name = $_.Name
    $ext = $_.Extension.ToLowerInvariant()
    (($Extensions -contains $ext) -or ($Names -contains $name)) -and
      (-not $name.EndsWith(".min.js")) -and
      (-not $name.EndsWith(".min.css")) -and
      (-not $name.EndsWith(".bundle.js")) -and
      (-not $name.EndsWith(".map"))
  })
}

Write-Host ""
Write-Host "Codex Security - Target Discovery" -ForegroundColor Cyan
Write-Host "Target : $TargetPath"
Write-Host "Config : $ConfigPath"
Write-Host "Files  : $($Files.Count) candidate source/config files"
Write-ScanEvent "target-discovery" "Discovered $($Files.Count) candidate source/config files" "info" "running"

if ($Files.Count -gt 0) {
  Write-Host ""
  Write-Host "By file type:" -ForegroundColor Cyan
  $Files | Group-Object { if ($_.Extension) { $_.Extension.ToLowerInvariant() } else { "[no extension]" } } |
    Sort-Object Count -Descending | Format-Table Count,Name -AutoSize

  Write-Host "First candidate targets:" -ForegroundColor Cyan
  $Files | Select-Object -First 30 -ExpandProperty FullName | ForEach-Object { Write-Host "  $_" }
  if ($Files.Count -gt 30) { Write-Host "  ... and $($Files.Count - 30) more" }
}

# Build a manifest of every candidate file so the HTML report can show
# scanned paths even when Semgrep produces no finding for that file.
$ManifestRows = @()
foreach ($File in $Files) {
  $Hash = ""
  try {
    $Hash = (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  } catch {
    $Hash = ""
  }

  $ManifestRows += [PSCustomObject]@{
    path = $File.FullName
    name = $File.Name
    extension = $File.Extension.ToLowerInvariant()
    bytes = [int64]$File.Length
    modifiedUtc = $File.LastWriteTimeUtc.ToString("o")
    sha256 = $Hash
    attributes = [string]$File.Attributes
    isHidden = [bool](($File.Attributes -band [IO.FileAttributes]::Hidden) -ne 0)
    isDotPath = [bool](($File.FullName -split '[\\/]') | Where-Object { $_ -match '^\.[^.]' } | Select-Object -First 1)
  }
}

$ManifestObject = [PSCustomObject]@{
  target = $TargetPath
  generatedUtc = [DateTime]::UtcNow.ToString("o")
  fileCount = $ManifestRows.Count
  files = $ManifestRows
}
$ManifestObject | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Manifest -Encoding UTF8
Write-Host "MANIFEST: $((Resolve-Path -LiteralPath $Manifest).Path)" -ForegroundColor DarkCyan
Write-ScanEvent "manifest" "Target manifest created with $($ManifestRows.Count) files" "info" "running"

$Python = Get-Command python -ErrorAction SilentlyContinue

if ($Mode -in @("cctv","/cctv")) { $LiveMonitor = $true }
if ($LiveMonitor -and $Python -and (Test-Path -LiteralPath "network-monitor.html")) {
  try {
    $script:MonitorProcess = Start-Process -FilePath $Python.Source -ArgumentList @("-m","http.server",$MonitorPort,"--bind","127.0.0.1") -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 700
    Start-Process "http://127.0.0.1:$MonitorPort/network-monitor.html"
    Write-ScanEvent "start" "Live network monitor opened on localhost:$MonitorPort" "info" "running"
  } catch {
    Write-Host "Live monitor could not start: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

if ($Python -and (Test-Path -LiteralPath "resolve-urls.py")) {
  $UrlArgs = @("resolve-urls.py","--manifest",$Manifest,"--output",$UrlReport)
  if ($ResolveUrls) { $UrlArgs += "--probe" }
  & $Python.Source @UrlArgs
  if (Test-Path -LiteralPath $UrlReport) {
    Write-Host "URL MAP : $((Resolve-Path -LiteralPath $UrlReport).Path)" -ForegroundColor DarkCyan
    if (-not $ResolveUrls) {
      Write-Host "          Static URL inventory only. Add -ResolveUrls for live final-URL/redirect verification." -ForegroundColor DarkGray
    }
    Write-ScanEvent "url-map" "URL inventory generated$(if ($ResolveUrls) { ' with live public resolution' } else { '' })" "info" "running"
  }
}

if ($Python -and (Test-Path -LiteralPath "analyze-code.py")) {
  & $Python.Source "analyze-code.py" --manifest $Manifest --urls $UrlReport --output $CodeReport
  if (Test-Path -LiteralPath $CodeReport) {
    Write-Host "CODE    : $((Resolve-Path -LiteralPath $CodeReport).Path)" -ForegroundColor DarkCyan
    Write-ScanEvent "code-analysis" "Deep code analysis generated" "info" "running"
  }
}

if ($Python -and (Test-Path -LiteralPath "preflight-analyze.py")) {
  $PreflightArgs = @("preflight-analyze.py","--manifest",$Manifest,"--urls",$UrlReport,"--code",$CodeReport,"--output",$PreflightReport)
  if ($CopyPublicCerts) { $PreflightArgs += "--copy-certs" }
  if ($CaptureAllCode) { $PreflightArgs += "--capture-code" }
  & $Python.Source @PreflightArgs
  if (Test-Path -LiteralPath $PreflightReport) {
    Write-Host "PREFLIGHT: $((Resolve-Path -LiteralPath $PreflightReport).Path)" -ForegroundColor Cyan
    Write-ScanEvent "preflight" "Before-scan privacy/anonymous target analysis generated" "info" "running"
  }
}

$argsList = @("scan","--config",$ConfigPath,"--json","--output",$Report)
if ($Strict) { $argsList += "--error" }
$argsList += $TargetPath

Write-Host ""
Write-Host "Running Semgrep..." -ForegroundColor Cyan
Write-ScanEvent "semgrep" "Semgrep security scan running" "info" "running"
& $Semgrep.Source @argsList
$ExitCode = $LASTEXITCODE
Write-ScanEvent "semgrep" "Semgrep completed with exit code $ExitCode" $(if ($ExitCode -eq 0) { "info" } else { "warning" }) "running"

if (Test-Path -LiteralPath $Report) {
  try {
    $data = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
    $results = @($data.results)
    $errors = @($results | Where-Object { $_.extra.severity -eq "ERROR" })
    $warnings = @($results | Where-Object { $_.extra.severity -eq "WARNING" })
    $info = @($results | Where-Object { $_.extra.severity -eq "INFO" })

    Write-Host ""
    Write-Host "Scan Summary" -ForegroundColor Cyan
    Write-Host "ERROR   : $($errors.Count)"
    Write-Host "WARNING : $($warnings.Count)"
    Write-Host "INFO    : $($info.Count)"
    Write-Host "TOTAL   : $($results.Count)"
    Write-Host "JSON    : $((Resolve-Path -LiteralPath $Report).Path)"

    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python -and (Test-Path -LiteralPath "build-modes.py")) {
      & $Python.Source "build-modes.py" --input $Report --manifest $Manifest --urls $UrlReport --output $ModeReport
      if (Test-Path -LiteralPath $ModeReport) {
        Write-Host "MODES   : $((Resolve-Path -LiteralPath $ModeReport).Path)" -ForegroundColor DarkCyan
        Write-ScanEvent "mode-analysis" "Security/privacy mode data generated" "info" "running"
      }
    }

    if ($Python -and (Test-Path -LiteralPath "analyze-network.py")) {
      & $Python.Source "analyze-network.py" --urls $UrlReport --semgrep $Report --code $CodeReport --manifest $Manifest --output $NetworkReport
      if (Test-Path -LiteralPath $NetworkReport) {
        Write-Host "NETWORK : $((Resolve-Path -LiteralPath $NetworkReport).Path)" -ForegroundColor DarkCyan
        Write-ScanEvent "network-analysis" "Network trace, route, map, visibility and real-IP analysis generated" "info" "running"
      }
    }

    if ($Python -and (Test-Path -LiteralPath "build-report.py")) {
      & $Python.Source "build-report.py" --input $Report --manifest $Manifest --urls $UrlReport --modes $ModeReport --code $CodeReport --network $NetworkReport --preflight $PreflightReport --mode $Mode --output $HtmlReport --target $TargetPath
      if (Test-Path -LiteralPath $HtmlReport) {
        $HtmlPath = (Resolve-Path -LiteralPath $HtmlReport).Path
        Write-Host "VISUAL  : $HtmlPath" -ForegroundColor Green
        Write-ScanEvent "report" "Visual report generated" "info" "running"
        if (-not $NoOpen -and -not $LiveMonitor) { Start-Process $HtmlPath }
      }
    } else {
      Write-Host "Visual report skipped: python or build-report.py was not found." -ForegroundColor Yellow
    }
  } catch {
    Write-Host "Could not summarize/build report: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-ScanEvent "report" "Report generation failed: $($_.Exception.Message)" "error" "error"
  }
}

Write-ScanEvent "complete" "Scan completed. Open semgrep-report.html for final analysis." "info" "complete"
if ($script:MonitorProcess -and -not $script:MonitorProcess.HasExited) {
  Start-Sleep -Milliseconds 1200
  Stop-Process -Id $script:MonitorProcess.Id -Force -ErrorAction SilentlyContinue
}

if ($CleanupLolaTemp) {
  $CleanupTargets = @($EventReport)
  if ($CaptureAllCode) { $CleanupTargets += ".lola-preflight\code" }
  foreach ($Item in $CleanupTargets) {
    try {
      if (Test-Path -LiteralPath $Item) {
        Remove-Item -LiteralPath $Item -Recurse -Force -ErrorAction Stop
        Write-Host "CLEANUP : removed Lola-generated temporary item $Item" -ForegroundColor DarkGray
      }
    } catch {
      Write-Host "Cleanup skipped for $Item : $($_.Exception.Message)" -ForegroundColor Yellow
    }
  }
}
exit $ExitCode

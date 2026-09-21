param(
  [Parameter(Position=0,Mandatory=$true)][string]$Apk,
  [string]$Analysis="apk-analysis.json",
  [string]$HtmlReport="apk-report.html",
  [ValidateSet("apk360","apkmanifest","apkpermissions","apkcomponents","apkurls","apkapi","apkkeys","apkcerts","apknative","apkwebview","apkcrypto","apkfiles","apkcode","apkrisk","apktools","/apk360","/apkmanifest","/apkpermissions","/apkcomponents","/apkurls","/apkapi","/apkkeys","/apkcerts","/apknative","/apkwebview","/apkcrypto","/apkfiles","/apkcode","/apkrisk","/apktools")]
  [string]$Mode="/apk360",
  [switch]$Decompile,
  [switch]$KeepDecompiled,
  [switch]$NoOpen,
  [switch]$CleanupLolaApk
)

$ErrorActionPreference="Stop"

function Fail([string]$Message) {
  Write-Host "[ERROR] $Message" -ForegroundColor Red
  exit 1
}

if (-not (Test-Path -LiteralPath $Apk -PathType Leaf)) { Fail "APK does not exist: $Apk" }
$ApkPath=(Resolve-Path -LiteralPath $Apk).Path
if ([IO.Path]::GetExtension($ApkPath).ToLowerInvariant() -ne ".apk") { Fail "Target must be an .apk file" }

$Python=Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { Fail "Python is required for APK analysis." }
if (-not (Test-Path -LiteralPath "analyze-apk.py")) { Fail "analyze-apk.py was not found." }

Write-Host ""
Write-Host "Lola APK Deep Scan" -ForegroundColor Cyan
Write-Host "APK     : $ApkPath"
Write-Host "Mode    : $Mode"

$Args=@("analyze-apk.py",$ApkPath,"--output",$Analysis)
if ($Decompile) { $Args += "--decompile" }
if ($KeepDecompiled) { $Args += "--keep-extracted" }

& $Python.Source @Args
$AnalyzeExit=$LASTEXITCODE
if ($AnalyzeExit -ne 0 -or -not (Test-Path -LiteralPath $Analysis)) {
  Fail "APK analysis failed."
}

Write-Host "ANALYSIS: $((Resolve-Path -LiteralPath $Analysis).Path)" -ForegroundColor DarkCyan

if (Test-Path -LiteralPath "build-apk-report.py") {
  & $Python.Source "build-apk-report.py" --input $Analysis --output $HtmlReport --mode $Mode
  if (Test-Path -LiteralPath $HtmlReport) {
    $ReportPath=(Resolve-Path -LiteralPath $HtmlReport).Path
    Write-Host "VISUAL  : $ReportPath" -ForegroundColor Green
    if (-not $NoOpen) { Start-Process $ReportPath }
  }
}

try {
  $Data=Get-Content -LiteralPath $Analysis -Raw | ConvertFrom-Json
  Write-Host ""
  Write-Host "APK Summary" -ForegroundColor Cyan
  Write-Host "Package : $($Data.summary.package)"
  Write-Host "SHA-256 : $($Data.summary.sha256)"
  Write-Host "Entries : $($Data.summary.entries)"
  Write-Host "SDK     : min $($Data.summary.minSdk) / target $($Data.summary.targetSdk)"
  Write-Host "Perms   : $($Data.summary.permissions)"
  Write-Host "Exported: $($Data.summary.exportedComponents)"
  Write-Host "URLs    : $($Data.summary.urls)"
  Write-Host "Native  : $($Data.summary.nativeLibraries)"
  Write-Host "Risks   : $($Data.summary.riskFindings)"
} catch {}

if ($CleanupLolaApk) {
  foreach ($Item in @(".lola-apk\decompiled")) {
    if (Test-Path -LiteralPath $Item) {
      Remove-Item -LiteralPath $Item -Recurse -Force -ErrorAction SilentlyContinue
      Write-Host "CLEANUP : removed Lola APK temporary item $Item" -ForegroundColor DarkGray
    }
  }
}

exit 0

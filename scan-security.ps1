param(
  [Parameter(Position=0)][string]$Target=".",
  [string]$Config="codex-security.yaml",
  [string]$Report="semgrep-results.json",
  [switch]$Strict
)

$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
  Write-Host "[ERROR] $Message" -ForegroundColor Red
  exit 1
}

if (-not (Test-Path -LiteralPath $Target)) { Fail "Target does not exist: $Target" }
if (-not (Test-Path -LiteralPath $Config)) { Fail "Config does not exist: $Config" }

$Semgrep = Get-Command semgrep -ErrorAction SilentlyContinue
if (-not $Semgrep) { Fail "Install Semgrep with: python -m pip install semgrep" }

$TargetPath = (Resolve-Path -LiteralPath $Target).Path
$ConfigPath = (Resolve-Path -LiteralPath $Config).Path

$Extensions = @(
  ".js",".jsx",".mjs",".cjs",".ts",".tsx",".html",".htm",
  ".json",".yaml",".yml",".xml",".md",".txt",".env",
  ".properties",".toml",".vue",".svelte"
)
$Names = @("Dockerfile","Containerfile",".env",".env.local",".env.production","nginx.conf","httpd.conf","Caddyfile")
$SkipDirs = @(".git","node_modules","vendor","dist","build","out",".next",".nuxt","coverage",".cache","tmp",".tmp","generated",".generated")

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
      (-not $name.EndsWith(".bundle.js")) -and
      (-not $name.EndsWith(".map"))
  })
}

Write-Host ""
Write-Host "Codex Security - Target Discovery" -ForegroundColor Cyan
Write-Host "Target : $TargetPath"
Write-Host "Config : $ConfigPath"
Write-Host "Files  : $($Files.Count) candidate source/config files"

if ($Files.Count -gt 0) {
  Write-Host ""
  Write-Host "By file type:" -ForegroundColor Cyan
  $Files |
    Group-Object { if ($_.Extension) { $_.Extension.ToLowerInvariant() } else { "[no extension]" } } |
    Sort-Object Count -Descending |
    Format-Table Count,Name -AutoSize

  Write-Host "First candidate targets:" -ForegroundColor Cyan
  $Files | Select-Object -First 30 -ExpandProperty FullName | ForEach-Object { Write-Host "  $_" }
  if ($Files.Count -gt 30) { Write-Host "  ... and $($Files.Count - 30) more" }
}

$argsList = @("scan","--config",$ConfigPath,"--json","--output",$Report)
if ($Strict) { $argsList += "--error" }
$argsList += $TargetPath

Write-Host ""
Write-Host "Running Semgrep..." -ForegroundColor Cyan
& $Semgrep.Source @argsList
$ExitCode = $LASTEXITCODE

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
    Write-Host "REPORT  : $((Resolve-Path -LiteralPath $Report).Path)"
  } catch {
    Write-Host "Could not summarize JSON report: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

exit $ExitCode

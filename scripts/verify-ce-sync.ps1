# Post-sync (or pre-sync dry-run) verification for Pro -> CE export.
# Does NOT copy files. Use publish-ce.ps1 -ExecuteSync to sync after audit passes.
param(
    [Parameter(Mandatory = $false)]
    [string]$CeRoot = "",
    [switch]$PreSyncOnly,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
$ProRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AuditPy = Join-Path $PSScriptRoot "audit_ce_export.py"

if (-not $CeRoot) {
    $CeRoot = Join-Path (Split-Path $ProRoot -Parent) "fastapi-ui-ce"
}
$CeRoot = [System.IO.Path]::GetFullPath($CeRoot)

Write-Host "=== CE Sync Verification ===" -ForegroundColor Cyan
Write-Host "Pro: $ProRoot"
Write-Host "CE:  $CeRoot"
Write-Host ""

# 1) Pro-side audit (simulated CE docs + exclude rules)
Write-Host "[1/3] Pro export audit (wording + exclude rules)..." -ForegroundColor Yellow
$auditArgs = @($AuditPy, "--pro-root", $ProRoot)
if ($Strict) { $auditArgs += "--strict" }
& python @auditArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "Pro export audit FAILED. Fix issues before sync." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host ""

if ($PreSyncOnly) {
    Write-Host "[2/3] Skipped CE directory checks (-PreSyncOnly)" -ForegroundColor DarkGray
    Write-Host "[3/3] Skipped" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Pre-sync checks OK. Next: .\scripts\publish-ce.ps1 -ExecuteSync" -ForegroundColor Green
    exit 0
}

# 2) Structural checks on CE tree (if exists)
Write-Host "[2/3] CE directory structure..." -ForegroundColor Yellow
if (-not (Test-Path -LiteralPath $CeRoot)) {
    Write-Host "CE root not found (OK if never synced): $CeRoot" -ForegroundColor DarkYellow
} else {
    $checks = @(
        @{ Path = "runner\WebEngine"; Expect = $false; Label = "engine source must not leak" },
        @{ Path = "docs"; Expect = $false; Label = "Pro internal docs must not leak" },
        @{ Path = "scripts\build_runner_client.ps1"; Expect = $false; Label = "runner build script must not leak" },
        @{ Path = "backend\app"; Expect = $true; Label = "backend app must exist" },
        @{ Path = "frontend\src"; Expect = $true; Label = "frontend src must exist" },
        @{ Path = "docs-site\index.md"; Expect = $true; Label = "docs-site must exist" }
    )
    foreach ($c in $checks) {
        $full = Join-Path $CeRoot $c.Path
        $exists = Test-Path -LiteralPath $full
        if ($exists -ne $c.Expect) {
            Write-Host "  FAIL: $($c.Path) — $($c.Label) (exists=$exists)" -ForegroundColor Red
            exit 1
        }
        Write-Host "  OK: $($c.Path)" -ForegroundColor Green
    }
}
Write-Host ""

# 3) CE-side wording audit (if CE exists)
Write-Host "[3/3] CE wording audit..." -ForegroundColor Yellow
if (Test-Path -LiteralPath $CeRoot) {
    $ceArgs = @($AuditPy, "--ce-root", $CeRoot)
    if ($Strict) { $ceArgs += "--strict" }
    & python @ceArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "CE wording audit FAILED." -ForegroundColor Red
        exit $LASTEXITCODE
    }
} else {
    Write-Host "  Skipped (no CE directory)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Verification complete." -ForegroundColor Green

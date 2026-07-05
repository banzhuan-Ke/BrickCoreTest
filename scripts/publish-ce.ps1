# CE publish workflow: audit -> (optional) sync -> verify -> print deploy checklist.
# Default: audit + dry-run only — does NOT write CE files or push git.
param(
    [Parameter(Mandatory = $false)]
    [string]$CeRoot = "",
    [switch]$ExecuteSync,
    [switch]$SkipAudit,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
$ProRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SyncScript = Join-Path $PSScriptRoot "sync-to-ce.ps1"
$VerifyScript = Join-Path $PSScriptRoot "verify-ce-sync.ps1"

if (-not $CeRoot) {
    $CeRoot = Join-Path (Split-Path $ProRoot -Parent) "fastapi-ui-ce"
}
$CeRoot = [System.IO.Path]::GetFullPath($CeRoot)

Write-Host "=== BrickCore CE Publish Workflow ===" -ForegroundColor Cyan
Write-Host "Pro:  $ProRoot"
Write-Host "CE:   $CeRoot"
Write-Host "Mode: $(if ($ExecuteSync) { 'SYNC (will write CE files)' } else { 'DRY-RUN + audit only' })"
Write-Host ""

if (-not $SkipAudit) {
    Write-Host "--- Step 1: Pre-sync audit ---" -ForegroundColor Yellow
    $verifyArgs = @("-File", $VerifyScript, "-CeRoot", $CeRoot, "-PreSyncOnly")
    if ($Strict) { $verifyArgs += "-Strict" }
    & powershell @verifyArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Abort: fix audit failures before sync." -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host ""
} else {
    Write-Host "--- Step 1: Skipped (-SkipAudit) ---" -ForegroundColor DarkGray
}

Write-Host "--- Step 2: Sync ---" -ForegroundColor Yellow
if ($ExecuteSync) {
    & $SyncScript -CeRoot $CeRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    & $SyncScript -CeRoot $CeRoot -DryRun
    Write-Host ""
    Write-Host "Dry-run complete (no files written). To sync:" -ForegroundColor DarkYellow
    Write-Host "  .\scripts\publish-ce.ps1 -ExecuteSync" -ForegroundColor DarkYellow
}
Write-Host ""

if ($ExecuteSync) {
    Write-Host "--- Step 3: Post-sync verify ---" -ForegroundColor Yellow
    $postArgs = @("-File", $VerifyScript, "-CeRoot", $CeRoot)
    if ($Strict) { $postArgs += "-Strict" }
    & powershell @postArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host ""
}

Write-Host "--- Manual steps (not run by this script) ---" -ForegroundColor Cyan
Write-Host @"

1. Runner zip (Pro only, not in CE Git):
   cd `"$ProRoot`"
   .\scripts\build_runner_client.ps1 -SkipPyInstaller -SkipRuntimeSetup
   Upload runner_client\dist\BrickCoreRunner.zip -> 网盘 + 系统管理·执行器发布

2. CE git commit & push:
   cd `"$CeRoot`"
   git status
   git add -A
   git commit -m "sync: <short description>"
   git push origin master

3. Demo server (SSH):
   cd /opt/BrickCore
   git pull origin master
   cd frontend && npm install && npm run build && cd ..
   docker compose up -d --build backend
   docker compose restart nginx

4. Optional: clear stale doc DB overrides on demo DB:
   mysql ... < scripts/ce-stubs/clear-builtin-doc-overrides.sql

5. Self-check on demo:
   curl -s http://<demo>/runner/version
   Test-Path runner\WebEngine  # must be False on CE clone

"@

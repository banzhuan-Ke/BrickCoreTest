# Sync Pro repo -> Community Edition (Plan 1.5)
# Excludes runner engine source; adds CE stubs from scripts/ce-stubs/
param(
    [Parameter(Mandatory = $false)]
    [string]$CeRoot = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $CeRoot) {
    $CeRoot = Join-Path (Split-Path $ProRoot -Parent) "fastapi-ui-ce"
}

$CeRoot = [System.IO.Path]::GetFullPath($CeRoot)
$ProRootNorm = $ProRoot.TrimEnd('\', '/')
$CeRootNorm = $CeRoot.TrimEnd('\', '/')

if ($CeRootNorm.StartsWith($ProRootNorm, [StringComparison]::OrdinalIgnoreCase)) {
    throw "CeRoot must not be inside ProRoot. Use a sibling folder like E:\project2026\fastapi-ui-ce"
}

$StubsDir = Join-Path $PSScriptRoot "ce-stubs"

$ExcludeDirs = @(
    "runner",
    ".git",
    ".cursor",
    ".qoder",
    ".idea",
    ".githooks",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    "__pycache__",
    "scripts\.cache",
    "runner_client\dist",
    "runner_client\venv",
    "frontend\node_modules",
    "frontend\dist",
    "backend\venv",
    "runner\browsers",
    "runner\venv",
    "runner\logs",
    "docs"
)

$ExcludeFiles = @(
    "scripts\build_runner_client.ps1",
    "scripts\migrate_to_test_catalog.py",
    "backend\static\runner\BrickCoreRunner.zip",
    "backend\check_migration.py",
    "backend\check_migration2.py",
    "backend\test_stream_debug.py",
    "import_ui_case.py",
    "restart-all.bat",
    "restart-dev.bat",
    "restart-fix.bat",
    "start-all.bat",
    "start-all-safe.bat",
    "start-local-simple.bat",
    "start-services-wsl.bat",
    "deploy-to-server.bat",
    "deploy-windows.bat",
    "deploy-frontend.bat",
    "deploy-frontend.sh",
    "deploy.sh",
    "upload-redis-image.bat"
)

# Wildcard patterns (relative path, use \)
$ExcludePatterns = @(
    "runner_client\upload*.bat",
    "runner_client\upload-server*.bat"
)

function Get-RelativeFilePath {
    param(
        [string]$Root,
        [string]$FullPath
    )
    if ([string]::IsNullOrWhiteSpace($FullPath)) { return $null }
    $rootFull = [System.IO.Path]::GetFullPath($Root)
    $fileFull = [System.IO.Path]::GetFullPath($FullPath)
    if (-not $fileFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        return $null
    }
    $skip = $rootFull.Length
    if ($fileFull.Length -gt $skip -and @('\', '/') -contains $fileFull[$skip].ToString()) {
        $skip++
    }
    if ($fileFull.Length -le $skip) { return $null }
    return $fileFull.Substring($skip)
}

function Test-ExcludedRelativePath {
    param([string]$RelativePath)
    if ([string]::IsNullOrWhiteSpace($RelativePath)) { return $true }
    $norm = $RelativePath -replace "/", "\"
    foreach ($d in $ExcludeDirs) {
        if ($norm -eq $d -or $norm.StartsWith($d + "\", [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    foreach ($f in $ExcludeFiles) {
        if ($norm -ieq $f) { return $true }
    }
    foreach ($p in $ExcludePatterns) {
        if ($norm -like $p) { return $true }
    }
    return $false
}

function Ensure-Dir {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-CeStubs {
    if (-not (Test-Path -LiteralPath $StubsDir)) {
        throw "Missing stubs directory: $StubsDir"
    }
    $runnerDir = Join-Path $CeRoot "runner"
    Ensure-Dir $runnerDir
    Copy-Item (Join-Path $StubsDir "runner-README.md") (Join-Path $runnerDir "README.md") -Force
    Copy-Item (Join-Path $StubsDir "LICENSE-RUNNER.md") (Join-Path $CeRoot "LICENSE-RUNNER.md") -Force

    $readmeTemplate = Get-ChildItem -Path (Join-Path $ProRoot "docs") -Recurse -Filter "README-CE.template.md" -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($readmeTemplate) {
        Copy-Item $readmeTemplate.FullName (Join-Path $CeRoot "README.md") -Force
        Write-Host "  README.md <- $($readmeTemplate.FullName)"
    } else {
        Write-Warning "README-CE.template.md not found under docs/"
    }

    $licensePath = Join-Path $CeRoot "LICENSE"
    if (-not (Test-Path -LiteralPath $licensePath)) {
        Copy-Item (Join-Path $StubsDir "LICENSE-APACHE.txt") $licensePath -Force
    }

    # CE demo stubs (paths via Join-Path — avoid \v etc. in quoted strings)
    $demoMaps = @(
        @("database-demo.sql", "database.sql"),
        @("database-demo-patch.sql", "database-demo-patch.sql"),
        @("database-demo-fix-labels.sql", "database-demo-fix-labels.sql"),
        @("docker-services.ce.yml", "docker-services.yml"),
        @("docker-compose.ce.yml", "docker-compose.yml"),
        @("env.example.ce", ".env.example"),
        @("backend.env.example.ce", (Join-Path "backend" ".env.example")),
        @("vitepress-config.mts", (Join-Path "docs-site" (Join-Path ".vitepress" "config.mts"))),
        @("docs-index-ce.md", (Join-Path "docs-site" "index.md")),
        @("docs-highlights-ce.md", (Join-Path "docs-site" (Join-Path "guide" "highlights.md"))),
        @("docs-runner-packaging-ce.md", (Join-Path "docs-site" (Join-Path "guide" "runner-packaging.md"))),
        @("docs-system-admin-ce.md", (Join-Path "docs-site" (Join-Path "guide" "system-admin.md")))
    )
    foreach ($pair in $demoMaps) {
        $srcName = $pair[0]
        $destRel = $pair[1]
        $srcPath = Join-Path $StubsDir $srcName
        if (-not (Test-Path -LiteralPath $srcPath)) {
            throw "Missing CE demo stub: $srcPath"
        }
        $destPath = Join-Path $CeRoot $destRel
        Ensure-Dir ([System.IO.Path]::GetDirectoryName($destPath))
        Copy-Item $srcPath $destPath -Force
        Write-Host "  CE demo: $destRel <- $srcName"
    }
}

Write-Host "=== Sync Pro -> CE (Plan 1.5) ==="
Write-Host "Pro: $ProRoot"
Write-Host "CE:  $CeRoot"
if ($DryRun) { Write-Host "[DryRun] No files will be written." -ForegroundColor Yellow }

Ensure-Dir $CeRoot

$copied = 0
$skipped = 0

Get-ChildItem -Path $ProRoot -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = Get-RelativeFilePath -Root $ProRootNorm -FullPath $_.FullName
    if ([string]::IsNullOrWhiteSpace($rel)) {
        $script:skipped++
        return
    }
    if (Test-ExcludedRelativePath $rel) {
        return
    }

    $dest = Join-Path $CeRoot $rel
    $destDir = [System.IO.Path]::GetDirectoryName($dest)
    if (-not $DryRun) {
        try {
            Ensure-Dir $destDir
            Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
        } catch {
            Write-Host "Copy failed: $rel" -ForegroundColor Red
            Write-Host $_.Exception.Message -ForegroundColor Red
            throw
        }
    }
    $script:copied++
}

if (-not $DryRun) {
    Write-CeStubs
}

$leak = Join-Path $CeRoot "runner\WebEngine"
if ((Test-Path -LiteralPath $leak) -and -not $DryRun) {
    throw "SAFETY: runner\WebEngine exists in CE after sync. Remove CE dir and retry."
}

Write-Host ""
$buildDocsPy = Join-Path $PSScriptRoot "build_showcase_docs.py"
if ((Test-Path -LiteralPath $buildDocsPy) -and -not $DryRun) {
    & python $buildDocsPy
    if ($LASTEXITCODE -ne 0) { throw "build_showcase_docs.py failed" }
}

Write-Host "Copied files: $copied (skipped outside-root: $skipped)"
if (-not $DryRun) {
    Write-Host "CE runner stub: OK"
    if (Test-Path -LiteralPath $leak) {
        Write-Host "FAIL: WebEngine leaked!" -ForegroundColor Red
        exit 1
    }
    Write-Host "Safety check: no runner\WebEngine - OK" -ForegroundColor Green
}
Write-Host ""
Write-Host "Next:"
Write-Host "  cd `"$CeRoot`""
Write-Host "  git status"
Write-Host "Doc: docs/其他文档/CE同步与发布手册.md"

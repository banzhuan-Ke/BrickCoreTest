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
    "runner_client\dist_staging",
    "runner_client\build",
    "runner_client\venv",
    "frontend\node_modules",
    "frontend\dist",
    "backend\venv",
    "backend\tests",
    "backend\.pytest_cache",
    "runner\browsers",
    "runner\venv",
    "runner\logs",
    "docs"
)

$ExcludeFiles = @(
    "scripts\build_runner_client.ps1",
    "scripts\migrate_to_test_catalog.py",
    "scripts\update_resume_2026.py",
    "scripts\reset-local-docker.ps1",
    "scripts\verify_runner_dist.ps1",
    "backend\static\runner\BrickCoreRunner.zip",
    "backend\check_migration.py",
    "backend\check_migration2.py",
    "backend\test_stream_debug.py",
    "backend\app\core\qa_judge_prompt.py",
    "backend\app\core\qa_eval_service.py",
    "backend\app\core\qa_eval_target_client.py",
    "backend\app\core\qa_eval_report.py",
    "backend\app\core\qa_eval_compare.py",
    "backend\app\routers\ai\qa_eval.py",
    "scripts\pack-demo-runner.ps1",
    "frontend\src\views\AI\AiQaEval.vue",
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

    Copy-Item (Join-Path $StubsDir "LICENSE-APACHE.txt") (Join-Path $CeRoot "LICENSE") -Force

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
        @("docs-ui-automation-ce.md", (Join-Path "docs-site" (Join-Path "guide" "ui-automation.md"))),
        @("docs-app-automation-ce.md", (Join-Path "docs-site" (Join-Path "guide" "app-automation.md"))),
        @("docs-system-admin-ce.md", (Join-Path "docs-site" (Join-Path "guide" "system-admin.md"))),
        @("docs-data-factory-ce.md", (Join-Path "docs-site" (Join-Path "guide" "data-factory.md"))),
        @("docs-ai-testing-ce.md", (Join-Path "docs-site" (Join-Path "guide" "ai-testing.md"))),
        @("docs-platform-assistant-ce.md", (Join-Path "docs-site" (Join-Path "guide" "platform-assistant.md"))),
        @("docs-runner-linux-server-ce.md", (Join-Path "docs-site" (Join-Path "guide" "runner-linux-server.md"))),
        @("docs-release-notes-ce.md", (Join-Path "docs-site" (Join-Path "guide" "release-notes.md"))),
        @("docs-runner-install-guide-ce.md", (Join-Path "docs-site" (Join-Path "guide" "runner-install-guide.md"))),
        @("runner-client-README.md", (Join-Path "runner_client" "README.md"))
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

    $mwEnv = Join-Path $StubsDir "demo-middleware.env"
    if (Test-Path -LiteralPath $mwEnv) {
        Copy-Item $mwEnv (Join-Path $CeRoot ".env") -Force
        Write-Host "  CE demo: .env <- demo-middleware.env (gitignored, do not push)"
    } else {
        Write-Warning "Missing $mwEnv — run: python scripts/generate_demo_middleware_env.py"
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
    $qaEvalPrune = @(
        "backend\app\core\qa_judge_prompt.py",
        "backend\app\core\qa_eval_service.py",
        "backend\app\core\qa_eval_target_client.py",
        "backend\app\core\qa_eval_report.py",
        "backend\app\core\qa_eval_compare.py",
        "backend\app\routers\ai\qa_eval.py",
        "frontend\src\views\AI\AiQaEval.vue"
    )
    foreach ($rel in $qaEvalPrune) {
        $target = Join-Path $CeRoot $rel
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Force
            Write-Host "  CE prune: removed $rel"
        }
    }
    $qaEvalStub = Join-Path $StubsDir "AiQaEval-stub.vue"
    $qaEvalDest = Join-Path $CeRoot "frontend\src\views\AI\AiQaEval.vue"
    if (Test-Path -LiteralPath $qaEvalStub) {
        Ensure-Dir ([System.IO.Path]::GetDirectoryName($qaEvalDest))
        Copy-Item $qaEvalStub $qaEvalDest -Force
        Write-Host "  CE stub: frontend\src\views\AI\AiQaEval.vue <- AiQaEval-stub.vue"
    }
    foreach ($rel in @("backend\tests", "backend\.pytest_cache")) {
        $target = Join-Path $CeRoot $rel
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
            Write-Host "  CE prune: removed $rel"
        }
    }
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
Write-Host "  .\scripts\verify-ce-sync.ps1 -CeRoot `"$CeRoot`""
Write-Host "  cd `"$CeRoot`""
Write-Host "  git status"
Write-Host "Doc: docs/其他文档/CE同步与发布手册.md"
Write-Host "Workflow: .\scripts\publish-ce.ps1 -ExecuteSync"

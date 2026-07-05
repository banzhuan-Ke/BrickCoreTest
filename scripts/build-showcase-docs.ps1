# Wrapper: generate showcase/docs from doc-center sources
$ErrorActionPreference = "Stop"
$ProRoot = if ($args -and $args[0]) { $args[0] } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
$py = Join-Path $PSScriptRoot "build_showcase_docs.py"
if (-not (Test-Path -LiteralPath $py)) { throw "Missing $py" }
& python $py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

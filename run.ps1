# One command from clone to running (Windows).
#
#   .\run.ps1          build the UI, build the warehouse if absent, serve on :8000
#   .\run.ps1 dev      API on :8000 plus the Vite dev server on :5173
#
# The API owns the DuckDB write lock, so the pipeline runs inside it rather
# than as a second process -- which is why "Ingest data" is a button.

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot

try {
    $PY = ".venv\Scripts\python.exe"

    if (-not (Test-Path $PY)) {
        Write-Host "Creating venv..."
        python -m venv .venv
    }

    & $PY -m pip install -q -r requirements.txt

    if (-not (Test-Path "warehouse\segosight.duckdb")) {
        Write-Host "Building the warehouse (first run)..."
        & $PY -m segosight.app.pipeline
    }

    $mode = if ($args.Count -gt 0) { $args[0] } else { "serve" }

    if ($mode -eq "dev") {
        Write-Host "API      -> http://127.0.0.1:8000"
        Write-Host "UI (dev) -> http://127.0.0.1:5173"

        $apiJob = Start-Job -ScriptBlock {
            param($root)
            Set-Location $root
            & ".venv\Scripts\python.exe" -m uvicorn segosight.app.api:app --reload --port 8000
        } -ArgumentList (Get-Location).Path

        try {
            Push-Location ui
            pnpm install --silent
            pnpm run dev
        } finally {
            Stop-Job $apiJob -ErrorAction SilentlyContinue
            Remove-Job $apiJob -ErrorAction SilentlyContinue
            Pop-Location
        }
    } else {
        if (-not (Test-Path "ui\dist")) {
            Write-Host "Building the UI..."
            Push-Location ui
            pnpm install --silent
            pnpm run build
            Pop-Location
        }

        Write-Host "SegoSight -> http://127.0.0.1:8000"
        & $PY -m uvicorn segosight.app.api:app --port 8000
    }
} finally {
    Pop-Location
}

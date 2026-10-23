$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    Write-Host 'Create the environment first: py -3 -m venv .venv'
    Write-Host 'Then install: .\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt'
    exit 1
}
& $pythonExecutable -m uvicorn coursepilot.api:app --host 127.0.0.1 --port 8000

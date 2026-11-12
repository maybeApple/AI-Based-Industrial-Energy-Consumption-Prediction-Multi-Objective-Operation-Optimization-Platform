param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run setup.ps1 first.' }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw 'Build frontend first: cd frontend; npm ci; npm run build' }
Write-Host "Industrial Energy: http://127.0.0.1:$Port"
Write-Host "API documentation: http://127.0.0.1:$Port/docs"
& $pythonPath -m uvicorn api.industrial_app:app --host 127.0.0.1 --port $Port

param([switch]$DownloadSteel)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Assert-Success { if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" } }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { python -m venv .venv; Assert-Success }
& .\.venv\Scripts\python.exe -m pip install -r requirements-industrial.txt
Assert-Success
if ($DownloadSteel) { & .\.venv\Scripts\python.exe -m scripts.prepare_industrial --download-steel }
else { & .\.venv\Scripts\python.exe -m scripts.prepare_industrial }
Assert-Success
Push-Location frontend
try {
    npm ci
    Assert-Success
    npm run build
    Assert-Success
} finally { Pop-Location }
Write-Host 'Ready. Run .\start.ps1 and open http://127.0.0.1:8000'

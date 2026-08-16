$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Write-Host "Installing build dependencies..."
& $python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt") "pyinstaller>=6.0"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Building PoE Helper..."
& $python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "poe_helper.spec")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$out = Join-Path $PSScriptRoot "dist\PoE Helper\PoE Helper.exe"
Write-Host ""
Write-Host "Build ready:"
Write-Host $out

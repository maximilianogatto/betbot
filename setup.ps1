$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "==> BetBot setup (Windows)"

if ($env:VIRTUAL_ENV) {
    $PythonBin = "python"
    Write-Host "Using active virtual environment: $env:VIRTUAL_ENV"
}
else {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            Write-Host "==> Creating virtual environment in .venv"
            & py -3 -m venv .venv
        }
        elseif (Get-Command python -ErrorAction SilentlyContinue) {
            Write-Host "==> Creating virtual environment in .venv"
            & python -m venv .venv
        }
        else {
            throw "Python 3 no está disponible. Instalá Python 3.11+ y volvé a ejecutar setup.ps1."
        }
    }

    $PythonBin = ".venv\Scripts\python.exe"
}

Write-Host "==> Upgrading pip"
& $PythonBin -m pip install --upgrade pip

Write-Host "==> Installing Python dependencies"
& $PythonBin -m pip install -r requirements.txt

Write-Host "==> Installing Playwright Chromium"
& $PythonBin -m playwright install chromium

Write-Host ""
Write-Host "Setup completado."
Write-Host ""
Write-Host "Siguientes pasos:"
Write-Host "1. Copiá .env.example a .env y completá TELEGRAM_BOT_TOKEN"
Write-Host "2. Si no tenías un entorno activo:"
Write-Host "   .\.venv\Scripts\Activate.ps1"
Write-Host "3. Ejecutá el bot:"
Write-Host "   python main.py"

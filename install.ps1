$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Fail([string]$Message) {
    throw $Message
}

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{ Launcher = "py"; Args = @("-3") }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{ Launcher = "python"; Args = @() }
    }

    Fail "No encontré Python 3.11+ en el sistema. Instalalo y volvé a intentar."
}

function Test-PythonVersion([hashtable]$PythonCommand) {
    & $PythonCommand.Launcher @($PythonCommand.Args) -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        Fail "Se necesita Python 3.11 o superior."
    }
}

$PythonCommand = Get-PythonCommand
Test-PythonVersion $PythonCommand

Write-Host ""
Write-Host "==> Instalador BetBot para Windows"
$PythonVersion = & $PythonCommand.Launcher @($PythonCommand.Args) --version
Write-Host "Usando intérprete: $PythonVersion"

if (-not (Test-Path "betbot\Scripts\python.exe")) {
    Write-Host ""
    Write-Host "==> Creando entorno virtual en betbot"
    & $PythonCommand.Launcher @($PythonCommand.Args) -m venv betbot
}
else {
    Write-Host ""
    Write-Host "==> Reutilizando entorno virtual existente (betbot)"
}

$PythonBin = "betbot\Scripts\python.exe"

Write-Host ""
Write-Host "==> Actualizando pip"
& $PythonBin -m pip install --upgrade pip

Write-Host ""
Write-Host "==> Instalando dependencias de Python"
& $PythonBin -m pip install -r requirements.txt

Write-Host ""
Write-Host "==> Instalando Playwright y Chromium"
& $PythonBin -m playwright install chromium

if (-not (Test-Path ".env")) {
    Write-Host ""
    Write-Host "==> Creando archivo .env a partir de .env.example"
    Copy-Item ".env.example" ".env"
}
else {
    Write-Host ""
    Write-Host "==> Archivo .env ya existente, lo dejo intacto"
}

Write-Host ""
Write-Host "Instalación completada."
Write-Host ""
Write-Host "Próximos pasos:"
Write-Host "1. Abrí el archivo .env y completá TELEGRAM_BOT_TOKEN"
Write-Host "2. Ejecutá el bot con:"
Write-Host "   .\run.ps1"

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Fail([string]$Message) {
    throw $Message
}

$ActivateScript = "betbot\Scripts\Activate.ps1"

if (-not (Test-Path $ActivateScript)) {
    Fail "No encontré el entorno virtual. Ejecutá primero .\install.ps1"
}

if (-not (Test-Path ".env")) {
    Fail "No encontré .env. Ejecutá primero .\install.ps1 y completá TELEGRAM_BOT_TOKEN"
}

. $ActivateScript

$TokenLine = Get-Content ".env" | Where-Object { $_ -match '^\s*TELEGRAM_BOT_TOKEN=' } | Select-Object -First 1
$TokenValue = ""

if ($TokenLine) {
    $TokenValue = ($TokenLine -replace '^\s*TELEGRAM_BOT_TOKEN=', '').Trim().Trim('"').Trim("'")
}

if ([string]::IsNullOrWhiteSpace($TokenValue) -or
    $TokenValue.StartsWith("123456789:") -or
    $TokenValue.Contains("replace_with_your_real_token") -or
    $TokenValue.Contains("reemplaza_este_valor_con_el_token_real_de_botfather")) {
    Fail "Completá TELEGRAM_BOT_TOKEN en .env antes de ejecutar el bot."
}

Write-Host "==> Iniciando BetBot"
python main.py

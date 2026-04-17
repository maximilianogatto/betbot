#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

step() {
  printf '\n==> %s\n' "$1"
}

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return
  fi

  if command -v python >/dev/null 2>&1; then
    printf '%s\n' "python"
    return
  fi

  fail "No encontré Python 3.11+ en el sistema. Instalalo y volvé a intentar."
}

check_python_version() {
  local python_bin="$1"

  if ! "$python_bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    fail "Se necesita Python 3.11 o superior."
  fi
}

PYTHON_BIN="$(find_python)"
check_python_version "$PYTHON_BIN"

step "Instalador BetBot para Linux/macOS"
printf 'Usando intérprete: %s\n' "$("$PYTHON_BIN" --version 2>&1)"

if [[ ! -d "betbot" ]]; then
  step "Creando entorno virtual en betbot"
  "$PYTHON_BIN" -m venv betbot
else
  step "Reutilizando entorno virtual existente (betbot)"
fi

# shellcheck disable=SC1091
source betbot/bin/activate

step "Actualizando pip"
python -m pip install --upgrade pip

step "Instalando dependencias de Python"
python -m pip install -r requirements.txt

step "Instalando Playwright y Chromium"
python -m playwright install chromium

if [[ ! -f ".env" ]]; then
  step "Creando archivo .env a partir de .env.example"
  cp .env.example .env
else
  step "Archivo .env ya existente, lo dejo intacto"
fi

cat <<'EOF'

Instalación completada.

Próximos pasos:
1. Abrí el archivo .env y completá TELEGRAM_BOT_TOKEN
2. Ejecutá el bot con:
   ./run.sh

Nota para Linux:
Si Playwright necesita dependencias del sistema, ejecutá:
python -m playwright install --with-deps chromium
EOF

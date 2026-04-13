#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "==> BetBot setup (Linux/macOS)"

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  PYTHON_BIN="python"
  echo "Using active virtual environment: ${VIRTUAL_ENV}"
else
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 no está disponible en el PATH."
    exit 1
  fi

  if [[ ! -d ".venv" ]]; then
    echo "==> Creating virtual environment in .venv"
    python3 -m venv .venv
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate
  PYTHON_BIN="python"
fi

echo "==> Upgrading pip"
"$PYTHON_BIN" -m pip install --upgrade pip

echo "==> Installing Python dependencies"
"$PYTHON_BIN" -m pip install -r requirements.txt

echo "==> Installing Playwright Chromium"
"$PYTHON_BIN" -m playwright install chromium

cat <<'EOF'

Setup completado.

Siguientes pasos:
1. Copiá .env.example a .env y completá TELEGRAM_BOT_TOKEN
2. Si no tenías un entorno activo:
   source .venv/bin/activate
3. Ejecutá el bot:
   python main.py

Nota para Linux:
Si Chromium falla por dependencias del sistema, ejecutá manualmente:
python -m playwright install --with-deps chromium
EOF

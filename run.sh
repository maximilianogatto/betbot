#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

if [[ ! -f "betbot/bin/activate" ]]; then
  fail "No encontré el entorno virtual. Ejecutá primero ./install.sh"
fi

if [[ ! -f ".env" ]]; then
  fail "No encontré .env. Ejecutá primero ./install.sh y completá TELEGRAM_BOT_TOKEN"
fi

# shellcheck disable=SC1091
source betbot/bin/activate

token_line="$(grep -E '^[[:space:]]*TELEGRAM_BOT_TOKEN=' .env | head -n 1 || true)"
token_value="${token_line#*=}"
token_value="${token_value%$'\r'}"

if [[ -z "${token_value//[[:space:]]/}" ]] || [[ "$token_value" == 123456789:* ]] || [[ "$token_value" == *"replace_with_your_real_token"* ]] || [[ "$token_value" == *"reemplaza_este_valor_con_el_token_real_de_botfather"* ]]; then
  fail "Completá TELEGRAM_BOT_TOKEN en .env antes de ejecutar el bot."
fi

printf '==> Iniciando BetBot\n'
python main.py

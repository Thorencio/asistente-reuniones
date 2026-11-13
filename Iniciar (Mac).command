#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "No encontré Python. Instálalo desde https://www.python.org/downloads/ y vuelve a abrir este archivo."
  open "https://www.python.org/downloads/"
  read -n 1 -s -r -p "Presiona una tecla para cerrar…"
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "Preparando la app por primera vez. Tarda 1 o 2 minutos…"
  python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt || {
    echo "Algo falló al instalar. Revisa tu conexión y vuelve a intentarlo."; exit 1; }
fi
nohup .venv/bin/python app.py >/dev/null 2>&1 &

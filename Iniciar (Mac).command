#!/bin/bash
cd "$(dirname "$0")" || exit 1
fin() { echo; read -n 1 -s -r -p "Presiona una tecla para cerrar…"; exit 1; }

# Quitar la "cuarentena" de macOS a los archivos descargados (evita bloqueos).
xattr -dr com.apple.quarantine . 2>/dev/null

# Buscar un Python 3.9+ que traiga tkinter (el de python.org lo trae; el de Homebrew a veces no).
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys, tkinter; assert sys.version_info >= (3,9)" >/dev/null 2>&1; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "No encontré un Python 3.9+ con soporte de ventanas (tkinter)."
  echo "Instala Python desde https://www.python.org/downloads/ (el instalador oficial) y vuelve a abrir este archivo."
  echo "Si usas Homebrew:  brew install python-tk"
  open "https://www.python.org/downloads/"
  fin
fi

CHECK="import tkinter, anthropic, googleapiclient, yaml, dotenv, markdown"
if [ -f .venv/instalado.ok ] && .venv/bin/python -c "$CHECK" >/dev/null 2>&1; then
  :
else
  [ -d .venv ] && echo "Rehaciendo el entorno de la app (estaba incompleto o viene de otro equipo)…"
  rm -rf .venv
  echo "Preparando la app por primera vez. Tarda 1 o 2 minutos…"
  if ! { "$PY" -m venv .venv && .venv/bin/python -m pip install --upgrade pip \
         && .venv/bin/python -m pip install -r requirements.txt && .venv/bin/python -c "$CHECK"; } > instalacion.log 2>&1; then
    echo "Algo falló al instalar. Últimas líneas del registro:"
    tail -15 instalacion.log
    rm -rf .venv
    fin
  fi
  echo ok > .venv/instalado.ok
  rm -f instalacion.log
fi
nohup .venv/bin/python app.py >/dev/null 2>&1 &

@echo off
title Asistente de Reuniones
cd /d "%~dp0"

rem --- Buscar Python ---
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY goto nopython

rem --- Primera vez: preparar el entorno ---
if not exist ".venv\Scripts\pythonw.exe" (
  echo Preparando la app por primera vez. Tarda 1 o 2 minutos...
  %PY% -m venv .venv || goto fallo
  ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto fallo
)

rem --- Abrir la app (sin ventana negra) ---
start "" ".venv\Scripts\pythonw.exe" app.py
exit /b

:nopython
echo.
echo No encontre Python en este PC.
echo Se abrira la pagina de descarga: instala Python y, en la primera pantalla
echo del instalador, marca la casilla "Add python.exe to PATH".
echo Luego vuelve a hacer doble clic en "Iniciar (Windows)".
echo.
start "" https://www.python.org/downloads/
pause
exit /b

:fallo
echo.
echo Algo fallo al instalar. Revisa tu conexion a internet y vuelve a intentarlo.
echo Si se repite, borra la carpeta .venv y prueba de nuevo.
pause

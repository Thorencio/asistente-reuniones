@echo off
title Crear ejecutable - Asistente de Reuniones
cd /d "%~dp0"
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
  echo No encontre Python. Instalalo desde https://www.python.org/downloads/
  echo marcando "Add python.exe to PATH", y vuelve a intentarlo.
  start "" https://www.python.org/downloads/
  pause
  exit /b
)
echo Creando "Asistente de Reuniones.exe". Tarda unos 3 a 5 minutos...
%PY% construir.py || (echo Fallo la construccion. & pause & exit /b)
echo.
echo Listo. Se abrira la carpeta con el ejecutable.
echo Puedes crear un acceso directo de "Asistente de Reuniones.exe" en el escritorio.
explorer "dist\Asistente de Reuniones"
pause

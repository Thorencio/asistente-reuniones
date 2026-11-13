@echo off
setlocal EnableExtensions
title Asistente de Reuniones
cd /d "%~dp0"

rem --- 1. No se puede ejecutar desde dentro de un .zip ---
echo "%~dp0" | findstr /i /c:"\AppData\Local\Temp\" >nul && goto enzip
if not exist "app.py" goto enzip

rem --- 2. Buscar un Python real (el alias de Microsoft Store no sirve) ---
set "PY="
py -3 -c "import sys; assert sys.version_info >= (3,9)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; assert sys.version_info >= (3,9)" >nul 2>nul && set "PY=python"
if not defined PY goto nopython

rem --- 3. Python debe traer tkinter (la parte de ventanas) ---
%PY% -c "import tkinter" >nul 2>nul || goto notk

rem --- 4. Revisar el entorno: si se copio de otro PC o quedo a medias, se rehace ---
if exist ".venv\instalado.ok" (
  ".venv\Scripts\python.exe" -c "import tkinter, anthropic, googleapiclient, yaml, dotenv, markdown" >nul 2>nul && goto abrir
  echo El entorno de la app esta danado o viene de otro computador. Lo rehago...
)
if exist ".venv" rmdir /s /q ".venv"

echo Preparando la app por primera vez. Tarda 1 o 2 minutos...
%PY% -m venv .venv > instalacion.log 2>&1 || goto fallo
".venv\Scripts\python.exe" -m pip install --upgrade pip >> instalacion.log 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt >> instalacion.log 2>&1 || goto fallo
".venv\Scripts\python.exe" -c "import tkinter, anthropic, googleapiclient, yaml, dotenv, markdown" >> instalacion.log 2>&1 || goto fallo
echo ok> ".venv\instalado.ok"
del instalacion.log >nul 2>nul

:abrir
rem --- 5. Abrir la app (sin ventana negra). Si falla al arrancar, mostrar el error ---
start "" ".venv\Scripts\pythonw.exe" app.py
exit /b

:enzip
echo.
echo Estas abriendo el archivo desde DENTRO del .zip.
echo Primero haz clic derecho sobre el .zip ^> "Extraer todo...", abre la carpeta
echo extraida y desde ahi haz doble clic en "Iniciar (Windows)".
echo.
pause
exit /b

:nopython
echo.
echo No encontre Python 3.9 o superior en este PC.
echo Se abrira la pagina de descarga: instala Python y, en la primera pantalla
echo del instalador, marca la casilla "Add python.exe to PATH".
echo (Si ya lo instalaste desde Microsoft Store y sigue fallando, instala el de python.org.)
echo Luego vuelve a hacer doble clic en "Iniciar (Windows)".
echo.
start "" https://www.python.org/downloads/
pause
exit /b

:notk
echo.
echo Tu Python no tiene "tcl/tk" (lo que dibuja las ventanas).
echo Abre el instalador de Python ^> "Modify" ^> marca "tcl/tk and IDLE" ^> Next ^> Install.
echo Luego vuelve a hacer doble clic en "Iniciar (Windows)".
echo.
pause
exit /b

:fallo
echo.
echo Algo fallo al instalar. Ultimas lineas del registro (instalacion.log):
echo ------------------------------------------------------------
powershell -NoProfile -Command "Get-Content -Tail 15 'instalacion.log'" 2>nul
echo ------------------------------------------------------------
echo Causas comunes:
echo  - Sin internet, o la red de tu empresa bloquea las descargas de Python (pip).
echo    Prueba con otra red (por ejemplo, compartiendo internet del celular).
echo  - Un antivirus bloqueo la carpeta. Mueve la carpeta a Documentos y reintenta.
if exist ".venv" rmdir /s /q ".venv"
pause
exit /b

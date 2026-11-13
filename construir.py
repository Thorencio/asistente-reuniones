#!/usr/bin/env python3
"""
Construye la app de escritorio para el sistema donde lo ejecutes:
  Windows -> dist/Asistente de Reuniones/Asistente de Reuniones.exe
  Mac     -> dist/Asistente de Reuniones.app
  Linux   -> dist/Asistente de Reuniones/Asistente de Reuniones

Uso:  python construir.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "Asistente de Reuniones"


def ensure_venv():
    """Construye dentro de un entorno virtual propio para no tocar el Python del sistema."""
    if sys.prefix != sys.base_prefix:
        return
    venv = HERE / ".venv-build"
    py = venv / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
    if not py.exists():
        print("Creando entorno de construcción…")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    sys.exit(subprocess.call([str(py), str(Path(__file__).resolve())]))


def main():
    ensure_venv()
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r",
                           str(HERE / "requirements.txt"), "pyinstaller>=6.0"])
    import PyInstaller.__main__

    args = [
        str(HERE / "app.py"),
        "--name", NAME,
        "--windowed",            # sin ventana de consola
        "--noconfirm",
        "--clean",
        # Google necesita sus documentos de "discovery" empaquetados.
        "--collect-data", "googleapiclient",
        "--hidden-import", "asistente",
        "--paths", str(HERE),
    ]
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "cl.asistente.reuniones"]
    PyInstaller.__main__.run(args)

    out = HERE / "dist" / (f"{NAME}.app" if sys.platform == "darwin" else NAME)
    print(f"\nListo: {out}")


if __name__ == "__main__":
    main()

"""Build the simcore engine for the desktop app.

Runs PyInstaller in folder ("onedir") mode and copies the result to
app/src-tauri/engine/, which Tauri bundles as an app resource. A folder
build starts quickly: a single-file build would unpack the ~250 MB engine
(mostly ITU-R climate maps) into a temporary directory on every launch.

Usage (from the repo root, in an environment with only the engine and
PyInstaller installed; a dev environment with pytest trips astropy's hook):
    python scripts/build_engine.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build" / "engine"
DEST = ROOT / "app" / "src-tauri" / "engine"
NAME = "simcore-server"


def main() -> None:
    data_sep = os.pathsep  # PyInstaller's --add-data separator
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onedir",
            "--name", NAME,
            "--distpath", str(BUILD_DIR / "dist"),
            "--workpath", str(BUILD_DIR / "work"),
            "--specpath", str(BUILD_DIR),
            # skyfield's bundled leap-second / Delta-T tables
            "--collect-data", "skyfield",
            # uvicorn picks its event loop / protocol modules dynamically
            "--collect-submodules", "uvicorn",
            # ITU-R climate maps, and the coordinate data ITU-Rpy's dependencies load
            "--collect-data", "itur",
            "--collect-data", "pyproj",
            "--collect-data", "astropy",
            # NRLMSIS coefficient files; without them its Fortran code stops the process
            "--collect-data", "pymsis",
            "--add-data", f"{ROOT / 'scenarios'}{data_sep}scenarios",
            str(ROOT / "engine" / "simcore" / "__main__.py"),
        ],
        check=True,
    )

    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(BUILD_DIR / "dist" / NAME, DEST)
    exe = DEST / (NAME + (".exe" if sys.platform == "win32" else ""))
    size_mb = sum(f.stat().st_size for f in DEST.rglob("*") if f.is_file()) / 1e6
    print(f"Engine: {exe} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()

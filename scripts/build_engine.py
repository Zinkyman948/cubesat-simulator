"""Build the simcore engine into a standalone executable for the desktop app.

Runs PyInstaller, then copies the result to
app/src-tauri/binaries/simcore-server-<target-triple>[.exe], the name Tauri
expects for the `binaries/simcore-server` sidecar.

Usage (from the repo root, with the engine and PyInstaller installed):
    python scripts/build_engine.py [--target <rust-target-triple>]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build" / "engine"
BINARIES = ROOT / "app" / "src-tauri" / "binaries"
NAME = "simcore-server"


def host_target_triple() -> str:
    try:
        out = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        sys.exit("rustc not found: install Rust, or pass --target <triple>")
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    sys.exit("could not determine the Rust host target triple")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", help="Rust target triple (default: rustc host)")
    args = parser.parse_args()
    target = args.target or host_target_triple()

    data_sep = os.pathsep  # PyInstaller's --add-data separator
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onefile",
            "--name", NAME,
            "--distpath", str(BUILD_DIR / "dist"),
            "--workpath", str(BUILD_DIR / "work"),
            "--specpath", str(BUILD_DIR),
            # skyfield's bundled leap-second / Delta-T tables
            "--collect-data", "skyfield",
            # uvicorn picks its event loop / protocol modules dynamically
            "--collect-submodules", "uvicorn",
            "--add-data", f"{ROOT / 'scenarios'}{data_sep}scenarios",
            str(ROOT / "engine" / "simcore" / "__main__.py"),
        ],
        check=True,
    )

    exe = ".exe" if sys.platform == "win32" else ""
    BINARIES.mkdir(parents=True, exist_ok=True)
    dest = BINARIES / f"{NAME}-{target}{exe}"
    shutil.copy2(BUILD_DIR / "dist" / f"{NAME}{exe}", dest)
    print(f"Engine sidecar: {dest}")


if __name__ == "__main__":
    main()

"""Version and release-notes helper.

    python scripts/release.py bump 0.3.0     # set the version everywhere
    python scripts/release.py check 0.3.0    # fail unless every file says 0.3.0
    python scripts/release.py notes 0.3.0    # print that version's CHANGELOG section

The app's version lives in app/package.json (tauri.conf.json points at it);
the Rust crate and the Python engine carry the same number.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

# file -> regex whose first group is the version
TOML_LIKE = {
    ROOT / "app" / "src-tauri" / "Cargo.toml": re.compile(r'^version = "([^"]+)"', re.M),
    ROOT / "engine" / "pyproject.toml": re.compile(r'^version = "([^"]+)"', re.M),
    ROOT / "engine" / "simcore" / "__init__.py": re.compile(r'^__version__ = "([^"]+)"', re.M),
}
PACKAGE_JSON = ROOT / "app" / "package.json"
PACKAGE_LOCK = ROOT / "app" / "package-lock.json"
CHANGELOG = ROOT / "CHANGELOG.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def current_versions() -> dict[str, str]:
    found = {str(p.relative_to(ROOT)): rx.search(read(p)).group(1) for p, rx in TOML_LIKE.items()}
    found[str(PACKAGE_JSON.relative_to(ROOT))] = json.loads(read(PACKAGE_JSON))["version"]
    return found


def bump(version: str) -> None:
    for path, rx in TOML_LIKE.items():
        text = read(path)
        m = rx.search(text)  # first match only: the package's own version
        write(path, text[: m.start(1)] + version + text[m.end(1):])
    for path in (PACKAGE_JSON, PACKAGE_LOCK):
        data = json.loads(read(path))
        data["version"] = version
        if path == PACKAGE_LOCK:
            data["packages"][""]["version"] = version
        write(path, json.dumps(data, indent=2) + "\n")
    print(f"Version set to {version}. Add a '## {version}' section to CHANGELOG.md, commit, then tag v{version}.")


def check(version: str) -> None:
    wrong = {f: v for f, v in current_versions().items() if v != version}
    if wrong:
        sys.exit(f"Version mismatch, expected {version}: {wrong}")
    if not notes_for(version):
        sys.exit(f"CHANGELOG.md has no '## {version}' section")
    print(f"All versions are {version}.")


def notes_for(version: str) -> str:
    # Sections look like "## 0.2.0 - 2026-11-12"; take everything up to the next "## ".
    m = re.search(rf"^## {re.escape(version)}\b.*?\n(.*?)(?=^## |\Z)", read(CHANGELOG), re.M | re.S)
    return m.group(1).strip() if m else ""


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in {"bump", "check", "notes"}:
        sys.exit(__doc__)
    command, version = sys.argv[1], sys.argv[2].removeprefix("v")
    if not SEMVER.match(version):
        sys.exit(f"Not a version (expected X.Y.Z): {version}")
    if command == "bump":
        bump(version)
    elif command == "check":
        check(version)
    else:
        print(notes_for(version))


if __name__ == "__main__":
    main()

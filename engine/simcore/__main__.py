"""`python -m simcore` entry point (also the PyInstaller entry script)."""

import sys

from simcore.cli import main

sys.exit(main())

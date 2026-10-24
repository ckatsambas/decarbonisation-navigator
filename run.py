"""Launcher used by PyInstaller and by double-clicking: same as `python -m navigator`."""
import sys

from navigator.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

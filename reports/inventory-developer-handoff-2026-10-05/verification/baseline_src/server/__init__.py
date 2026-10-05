"""ARA Map: mapa interactivo de terrenos para análisis de adquisición.

Importing this package puts the bundled copy of openpyxl on the import path so
the application runs on a stock macOS Python with nothing installed. The path
is APPENDED, so a system-wide openpyxl still wins when one is present.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "python"

if _VENDOR.is_dir():
    _path = str(_VENDOR)
    if _path not in sys.path:
        sys.path.append(_path)

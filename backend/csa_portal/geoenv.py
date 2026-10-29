"""Point the raster libraries at their own bundled projection data.

Other software on the machine (PostGIS, QGIS) can set PROJ_LIB or PROJ_DATA to its own, older
projection database, which rasterio then fails to read. This must run before rasterio is imported.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def use_bundled_proj() -> None:
    spec = importlib.util.find_spec("rasterio")
    if spec is None or spec.origin is None:
        return
    bundled = Path(spec.origin).parent / "proj_data"
    if bundled.is_dir():
        os.environ["PROJ_DATA"] = str(bundled)
        os.environ["PROJ_LIB"] = str(bundled)

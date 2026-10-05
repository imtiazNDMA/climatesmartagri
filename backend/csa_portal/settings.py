"""Where the backend finds its files. Every value can be overridden by an environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BASEMAP_STYLE_URL = "https://tiles.openfreemap.org/styles/positron"


@dataclass(frozen=True)
class Settings:
    catalogue_path: Path
    boundaries_dir: Path
    basemap_style_url: str
    data_dir: Path = BACKEND_DIR / "data"
    rasters_dir: Path = BACKEND_DIR / "rasters"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            catalogue_path=Path(
                os.environ.get("CSA_CATALOGUE_PATH", BACKEND_DIR / "catalogue.json")
            ),
            boundaries_dir=Path(
                os.environ.get("CSA_BOUNDARIES_DIR", BACKEND_DIR / "boundaries")
            ),
            basemap_style_url=os.environ.get(
                "CSA_BASEMAP_STYLE_URL", DEFAULT_BASEMAP_STYLE_URL
            ),
            data_dir=Path(os.environ.get("CSA_DATA_DIR", BACKEND_DIR / "data")),
            rasters_dir=Path(os.environ.get("CSA_RASTERS_DIR", BACKEND_DIR / "rasters")),
        )

"""Where the backend finds its files. Every value can be overridden by an environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BASEMAP_STYLE_URL = "https://tiles.openfreemap.org/styles/positron"


def read_env_file(path: Path) -> dict[str, str]:
    """The NAME=value lines of a .env file. Blank lines and lines starting with # are skipped."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values
    for line in lines:
        name, sep, value = line.strip().partition("=")
        if sep and name and not name.startswith("#"):
            values[name.strip()] = value.strip().strip("\"'")
    return values


@dataclass(frozen=True)
class Settings:
    catalogue_path: Path
    boundaries_dir: Path
    basemap_style_url: str
    data_dir: Path = BACKEND_DIR / "data"
    rasters_dir: Path = BACKEND_DIR / "rasters"
    # The weather forecast: its list of layers, where fetched files are kept, and the PMD account.
    forecast_layers_path: Path = BACKEND_DIR / "forecast_layers.json"
    forecast_dir: Path = BACKEND_DIR / "forecast"
    pmd_url: str = ""
    pmd_user: str = ""
    pmd_pass: str = ""
    pmd_cert_sha256: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        # The environment wins; the .env file at the repo root fills in what it does not set.
        env = {**read_env_file(BACKEND_DIR.parent / ".env"), **os.environ}
        return cls._from(env)

    @classmethod
    def _from(cls, environ: dict[str, str]) -> Settings:
        return cls(
            catalogue_path=Path(
                environ.get("CSA_CATALOGUE_PATH", BACKEND_DIR / "catalogue.json")
            ),
            boundaries_dir=Path(
                environ.get("CSA_BOUNDARIES_DIR", BACKEND_DIR / "boundaries")
            ),
            basemap_style_url=environ.get(
                "CSA_BASEMAP_STYLE_URL", DEFAULT_BASEMAP_STYLE_URL
            ),
            data_dir=Path(environ.get("CSA_DATA_DIR", BACKEND_DIR / "data")),
            rasters_dir=Path(environ.get("CSA_RASTERS_DIR", BACKEND_DIR / "rasters")),
            forecast_layers_path=Path(
                environ.get("CSA_FORECAST_LAYERS_PATH", BACKEND_DIR / "forecast_layers.json")
            ),
            forecast_dir=Path(environ.get("CSA_FORECAST_DIR", BACKEND_DIR / "forecast")),
            pmd_url=environ.get("CSA_PMD_URL", ""),
            pmd_user=environ.get("CSA_PMD_USER", ""),
            pmd_pass=environ.get("CSA_PMD_PASS", ""),
            pmd_cert_sha256=environ.get("CSA_PMD_CERT_SHA256", ""),
        )

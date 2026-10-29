"""Where the backend finds its files. Every value can be overridden by an environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BASEMAP_STYLE_URL = "https://tiles.openfreemap.org/styles/positron"
DEFAULT_CROP_MODEL_DIR = BACKEND_DIR / "models" / "crop-classification" / "improved-002"
DEFAULT_FIVE_CROP_MODEL_DIR = BACKEND_DIR / "models" / "crop-classification" / "five-crop-001"
DEFAULT_CROP_GUIDANCE = BACKEND_DIR / "crop_guidance.json"
DEFAULT_HAZARD_PRODUCTS = BACKEND_DIR / "hazard_products.json"
DEFAULT_HAZARD_MODELS = BACKEND_DIR / "hazard_models.json"


def positive_float(value: str, fallback: float) -> float:
    try:
        parsed = float(value)
    except ValueError:
        return fallback
    return parsed if 0 < parsed < float("inf") else fallback


def positive_int(value: str, fallback: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return fallback
    return parsed if parsed > 0 else fallback


def optional_path(value: str) -> Path | None:
    """A path, or None for an empty value: an empty CSA_AI_DB turns the AI store off (the browser tests do this)."""
    return Path(value) if value else None


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
    # Rice and maize stay on improved-002: it covers their pests and healthy plants (#71).
    crop_model_dir: Path = DEFAULT_CROP_MODEL_DIR
    # Cotton, wheat and sugarcane.
    five_crop_model_dir: Path = DEFAULT_FIVE_CROP_MODEL_DIR
    # Symptoms and prevention per class; treatment steps only once reviewed (#15).
    crop_guidance_path: Path = DEFAULT_CROP_GUIDANCE
    hazard_products_path: Path = DEFAULT_HAZARD_PRODUCTS
    hazard_models_path: Path = DEFAULT_HAZARD_MODELS
    # Local OpenAI-compatible model server (LM Studio by default).
    lm_studio_url: str = "http://127.0.0.1:1234"
    lm_studio_model: str = "qwen/qwen3.8-27b"
    lm_studio_api_key: str = ""
    lm_studio_timeout: float = 60
    # The AI store and tracing. Without a database (the default when built directly, as tests do) answers are
    # still traced in memory, but nothing is kept.
    ai_db_path: Path | None = None
    trace_content: bool = False
    trace_retention_days: int = 30
    ai_concurrency: int = 1
    ai_queue_seconds: float = 5
    otlp_endpoint: str = ""
    # The evaluation judge: a second local model, of another family than the assistant's.
    judge_url: str = "http://127.0.0.1:1234"
    judge_model: str = ""
    # The AI Ops dashboard's API token. Unset, the /api/ops routes are not mounted at all.
    ops_token: str = ""

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
            crop_model_dir=Path(environ.get("CSA_CROP_MODEL_DIR", DEFAULT_CROP_MODEL_DIR)),
            five_crop_model_dir=Path(environ.get("CSA_FIVE_CROP_MODEL_DIR", DEFAULT_FIVE_CROP_MODEL_DIR)),
            crop_guidance_path=Path(environ.get("CSA_CROP_GUIDANCE", DEFAULT_CROP_GUIDANCE)),
            hazard_products_path=Path(environ.get("CSA_HAZARD_PRODUCTS", DEFAULT_HAZARD_PRODUCTS)),
            hazard_models_path=Path(environ.get("CSA_HAZARD_MODELS", DEFAULT_HAZARD_MODELS)),
            lm_studio_url=environ.get("CSA_LM_STUDIO_URL", "http://127.0.0.1:1234"),
            lm_studio_model=environ.get("CSA_LM_STUDIO_MODEL", "qwen/qwen3.8-27b"),
            lm_studio_api_key=environ.get("CSA_LM_STUDIO_API_KEY", ""),
            lm_studio_timeout=positive_float(environ.get("CSA_LM_STUDIO_TIMEOUT", "60"), 60),
            ai_db_path=optional_path(environ.get("CSA_AI_DB", str(BACKEND_DIR / "ai.db"))),
            trace_content=environ.get("CSA_TRACE_CONTENT", "") == "1",
            trace_retention_days=positive_int(environ.get("CSA_TRACE_RETENTION_DAYS", "30"), 30),
            ai_concurrency=positive_int(environ.get("CSA_AI_CONCURRENCY", "1"), 1),
            ai_queue_seconds=positive_float(environ.get("CSA_AI_QUEUE_SECONDS", "5"), 5),
            otlp_endpoint=environ.get("CSA_OTLP_ENDPOINT", ""),
            # Empty counts as unset: copying .env.example leaves CSA_JUDGE_URL= with no value.
            judge_url=environ.get("CSA_JUDGE_URL") or environ.get("CSA_LM_STUDIO_URL") or "http://127.0.0.1:1234",
            judge_model=environ.get("CSA_JUDGE_MODEL", ""),
            ops_token=environ.get("CSA_OPS_TOKEN", ""),
        )

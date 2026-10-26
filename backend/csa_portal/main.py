"""The portal's HTTP API. Start with: uvicorn csa_portal.main:create_app --factory"""

from __future__ import annotations

import functools
import logging
import sqlite3
import urllib.parse
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from .geoenv import use_bundled_proj

use_bundled_proj()  # before anything imports rasterio

import rasterio  # noqa: E402
import rasterio.errors  # noqa: E402
import httpx  # noqa: E402
from fastapi import FastAPI, HTTPException, Query, Request, Response  # noqa: E402
from rasterio.warp import transform_bounds  # noqa: E402
from titiler.core.dependencies import parse_color  # noqa: E402
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers  # noqa: E402
from titiler.core.factory import TilerFactory  # noqa: E402

from .catalogue import Layer, load_catalogue  # noqa: E402
from .ai.agents.assistant import AssistantClient, AssistantService, add_assistant_routes  # noqa: E402
from .crop_classification import CropClassifier, add_crop_classification_routes  # noqa: E402
from .facts import Facts  # noqa: E402
from .land_cover_mpc import (  # noqa: E402
    SUPPORTED_YEARS,
    LandCoverResolver,
    MpcLandCoverError,
    MpcLandCoverResolver,
    pakistan_geometry,
)
from .ai.model import LmStudioModel  # noqa: E402
from .ai.otlp import OtlpExporter  # noqa: E402
from .ai.store import AiStore, StoreError  # noqa: E402
from .ai.tracing import Tracer  # noqa: E402
from .hazards import add_hazard_routes, load_hazards  # noqa: E402
from .hazard_models import DerivedRegistryError, DerivedService, load_hazard_models  # noqa: E402
from .forecast import (  # noqa: E402
    ForecastService,
    ForecastSource,
    RegistryError,
    add_forecast_routes,
    load_registry,
)
from .pmd import PmdClient  # noqa: E402
from .places import COUNTRY_ID, BoundaryError, Place, load_places, no_places  # noqa: E402
from .sections import GeoJsonProvider, SectionDataProvider, build_providers  # noqa: E402
from .settings import Settings  # noqa: E402

TileProvider = Callable[[int, int, int, int | None], tuple[bytes, str] | None]

MAX_ZOOM = 24
COG_PREFIX = "/api/cog"

logger = logging.getLogger("uvicorn.error")


def _error(status: int, message: str, reason: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"message": message, "reason": reason})


# How a failure to resolve an observation reaches the browser.
_OBSERVATION_FAILURES = {
    "year-out-of-range": (422, "year-out-of-range"),
    "no-data": (404, "no-data"),
    "invalid-source": (502, "invalid-source"),
    "incomplete-source": (502, "incomplete-source"),
    "invalid-upstream-response": (502, "invalid-upstream-response"),
    "upstream-rejected": (502, "upstream-rejected"),
    "upstream-unavailable": (503, "upstream-unavailable"),
    "upstream-timeout": (504, "upstream-timeout"),
    "invalid-boundaries": (500, "invalid-boundaries"),
}


def _observation_error(error: MpcLandCoverError) -> HTTPException:
    status, reason = _OBSERVATION_FAILURES.get(error.code, (502, "upstream-unavailable"))
    return _error(status, str(error), reason)


@functools.lru_cache(maxsize=64)
def _raster_bounds(path: Path, mtime: float) -> list[float] | None:
    """Where a raster has data, as west, south, east, north in degrees; the map asks for no tiles beyond it.

    Keyed on the file's modified time, so a re-prepared raster is measured afresh."""
    try:
        with rasterio.open(path) as source:
            return [round(v, 6) for v in transform_bounds(source.crs, "EPSG:4326", *source.bounds)]
    except rasterio.errors.RasterioError as err:
        logger.warning("Could not read the extent of %s: %s", path, err)
        return None


def _describe_forecast(forecast: ForecastService | None, derived: DerivedService | None) -> dict[str, Any] | None:
    """The forecast description, with any computed hazard models listed alongside the fetched layers."""
    if forecast is None:
        return None
    body = forecast.describe()
    if derived is not None:
        extra = derived.describe()
        body["groups"] = [*body["groups"], *extra["groups"]]
        body["layers"] = [*body["layers"], *extra["layers"]]
    return body


def _build_tracer(settings: Settings) -> Tracer:
    """The tracer the settings ask for. A store that cannot be opened leaves the portal answering without one."""
    exporter = OtlpExporter(settings.otlp_endpoint) if settings.otlp_endpoint else None
    if settings.ai_db_path is None:
        return Tracer(None, capture_content=settings.trace_content, exporter=exporter)
    try:
        store = AiStore(settings.ai_db_path)
    except (StoreError, sqlite3.Error, OSError) as err:
        logger.error("The AI store could not be opened; answering without traces: %s", err)
        return Tracer(None, capture_content=settings.trace_content, exporter=exporter, unavailable=str(err))
    cutoff = datetime.now(UTC) - timedelta(days=settings.trace_retention_days)
    try:
        removed = store.delete_live_traces_before(cutoff)
    except sqlite3.Error as err:
        # A read-only or locked file opens fine; this delete is the first write that finds out.
        store.close()
        logger.error("The AI store could not be written; answering without traces: %s", err)
        return Tracer(None, capture_content=settings.trace_content, exporter=exporter, unavailable=str(err))
    if removed:
        logger.info("Deleted %d live traces older than %d days", removed, settings.trace_retention_days)
    return Tracer(store, capture_content=settings.trace_content, exporter=exporter)


def create_app(
    settings: Settings | None = None,
    section_providers: Mapping[str, SectionDataProvider] | None = None,
    tile_providers: Mapping[str, TileProvider] | None = None,
    geojson_providers: Mapping[str, GeoJsonProvider] | None = None,
    forecast_source: ForecastSource | None = None,
    crop_classifier: CropClassifier | None = None,
    assistant_client: AssistantClient | None = None,
    tracer: Tracer | None = None,
    land_cover: LandCoverResolver | None = None,
    land_cover_error: str | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    tracer = tracer or _build_tracer(settings)
    catalogue = load_catalogue(settings.catalogue_path)
    boundaries_error: str | None = None
    try:
        places = load_places(settings.boundaries_dir)
    except BoundaryError as err:
        # Bad boundary files must not take the portal down; run without them and say why.
        boundaries_error = str(err)
        logger.error("Boundaries could not be loaded: %s", err)
        places = no_places()
    # Providers not passed in are built from the prepared files in the data folder.
    default_sections, default_geojson = build_providers(settings.data_dir, settings.boundaries_dir)
    section_data = dict(default_sections if section_providers is None else section_providers)
    geojson = dict(default_geojson if geojson_providers is None else geojson_providers)
    tiles = dict(tile_providers or {})
    sections = {section.id: section for section in catalogue.sections}
    layers = {layer.id: layer for layer in catalogue.layers}

    # --- The annual land-classification observation, served from Microsoft Planetary Computer.
    wants_observation = any(layer.tile_source == "mpc" for layer in catalogue.layers)
    if land_cover is None and land_cover_error is None and wants_observation:
        try:
            land_cover = MpcLandCoverResolver(
                httpx.Client(timeout=30.0, follow_redirects=True),
                pakistan_geometry(settings.boundaries_dir),
            )
        except MpcLandCoverError as err:
            # Without the country's outline the catalogue cannot be asked what covers it;
            # the portal still starts, and says why the layer has no tiles.
            land_cover_error = str(err)
            logger.error("The annual land-classification service could not start: %s", err)

    app = FastAPI(title="CSA Portal")

    classifier = crop_classifier or CropClassifier(settings.crop_model_dir)
    add_crop_classification_routes(app, classifier)
    hazards = load_hazards(settings.hazard_products_path)

    # --- Land-cover rasters, served by TiTiler from converted (cloud-optimized) files.
    def raster_file(layer: Layer) -> Path | None:
        """The converted file behind a raster layer, if the layer has one and it exists."""
        if layer.kind != "raster" or not layer.source:
            return None
        path = settings.rasters_dir / layer.source
        return path if path.is_file() else None

    def served(layer: Layer) -> dict[str, Any]:
        """A layer as the catalogue reports it: a raster is ready only once its file is converted."""
        body = layer.model_dump()
        body["tile_url"] = None
        body["bounds"] = None
        if layer.tile_source == "mpc":
            # Its tiles come from the annual observation, so it is ready exactly when that service is.
            if land_cover is None:
                body["status"] = "no-data"
        elif layer.kind == "raster" and layer.source:
            path = raster_file(layer)
            if path is None:
                body["status"] = "no-data"
            elif layer.status == "ready":
                body["tile_url"] = f"{COG_PREFIX}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?layer={layer.id}"
                body["bounds"] = _raster_bounds(path, path.stat().st_mtime)
        return body

    def cog_layer(layer_id: str) -> Layer:
        layer = layers.get(layer_id)
        if layer is None or layer.kind != "raster" or not layer.source:
            raise _error(404, f"Unknown raster layer '{layer_id}'", "not-found")
        return layer

    def cog_path(layer: Annotated[str, Query(description="A raster layer id from the catalogue")]) -> str:
        """TiTiler normally opens any path or URL it is given; here it only opens catalogue layers."""
        path = raster_file(cog_layer(layer))
        if path is None:
            raise _error(404, f"Layer '{layer}' has not been converted yet", "no-data")
        return str(path)

    def cog_colormap(layer: Annotated[str, Query()]) -> dict[int, tuple[int, int, int, int]] | None:
        """Colours come from the layer's legend, so the map and its key cannot disagree."""
        legend = cog_layer(layer).legend
        if legend is None or legend.type != "classes":
            return None
        colours = {int(item.value): parse_color(item.colour) for item in legend.items if item.value is not None}
        return colours or None

    @app.middleware("http")
    async def cog_cache_headers(request: Request, call_next: Any) -> Response:
        """Let a browser keep a land-cover tile for an hour: the rasters change only when they are re-prepared."""
        response = await call_next(request)
        if request.url.path.startswith(f"{COG_PREFIX}/tiles/"):
            response.headers["Cache-Control"] = "public, max-age=3600" if response.status_code == 200 else "no-store"
        return response

    cog = TilerFactory(router_prefix=COG_PREFIX, path_dependency=cog_path, colormap_dependency=cog_colormap)
    app.include_router(cog.router, prefix=COG_PREFIX, tags=["Land cover"])
    add_exception_handlers(app, DEFAULT_STATUS_CODES)

    # --- Weather forecast, fetched from PMD on demand. Only for a catalogue whose sections show forecasts.
    forecast: ForecastService | None = None
    derived: DerivedService | None = None
    if any(section.kind in {"forecast", "hazards"} for section in catalogue.sections):
        if forecast_source is None and settings.pmd_url and settings.pmd_user:
            forecast_source = PmdClient(
                settings.pmd_url, settings.pmd_user, settings.pmd_pass, settings.pmd_cert_sha256
            )
        try:
            forecast = ForecastService(
                load_registry(settings.forecast_layers_path), forecast_source, settings.forecast_dir
            )
        except RegistryError as err:
            # A bad layer list must not take the portal down; the section shows as having no data.
            logger.error("Forecast layers could not be loaded: %s", err)
        if forecast is not None:
            try:
                derived = DerivedService(forecast, load_hazard_models(settings.hazard_models_path))
            except DerivedRegistryError as err:
                logger.error("Hazard models could not be loaded: %s", err)
            add_forecast_routes(app, forecast, derived)

    district_risk = add_hazard_routes(app, hazards, places, forecast, derived)
    facts = Facts(catalogue, places, section_data, district_risk)
    local_assistant = assistant_client or LmStudioModel(
        settings.lm_studio_url,
        settings.lm_studio_model,
        settings.lm_studio_timeout,
        settings.lm_studio_api_key,
    )
    add_assistant_routes(
        app,
        AssistantService(
            catalogue,
            places,
            facts,
            local_assistant,
            settings.lm_studio_model,
            forecast_description=_describe_forecast(forecast, derived),
            hazard_description=hazards.model_dump(mode="json"),
            local_model=urllib.parse.urlparse(settings.lm_studio_url).hostname in {"127.0.0.1", "localhost", "::1"},
            tracer=tracer,
            concurrency=settings.ai_concurrency,
            queue_seconds=settings.ai_queue_seconds,
        ),
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        body = {
            "status": "ok",
            "boundaries_loaded": places.loaded,
            "boundaries_error": boundaries_error,
            "crop_classifier_configured": classifier.configured,
            "assistant_model": settings.lm_studio_model,
            "tracing": tracer.status,
            "tracing_error": tracer.unavailable,
            "tracing_failures": tracer.failures,
            "layers": {
                layer.id: places.loaded
                if layer.kind == "boundary"
                else layer.id in tiles or layer.id in geojson or raster_file(layer) is not None
                for layer in catalogue.layers
            },
        }
        if wants_observation:
            body["land_cover"] = {
                "status": "ready" if land_cover is not None else "unavailable",
                "years": list(SUPPORTED_YEARS),
                "error": land_cover_error,
            }
        return body

    @app.get("/api/catalogue")
    def get_catalogue() -> dict[str, Any]:
        return {
            "basemap_style_url": settings.basemap_style_url,
            "sections": [section.model_dump() for section in catalogue.sections],
            "layers": [served(layer) for layer in catalogue.layers],
            "forecast": _describe_forecast(forecast, derived),
        }

    @app.get("/api/land-cover/observation")
    def land_cover_observation(response: Response, year: int | None = None) -> dict[str, Any]:
        """The tiles for one annual land-classification observation, and where they came from.

        The year is the observation the map shows; without one, the latest published year is served.
        """
        if land_cover is None:
            raise _error(
                503,
                "The annual land-classification service is not available",
                "not-configured",
            )
        if year is not None and year not in SUPPORTED_YEARS:
            raise _error(
                422,
                f"Year {year} is outside {SUPPORTED_YEARS[0]}-{SUPPORTED_YEARS[-1]}",
                "year-out-of-range",
            )
        try:
            resolved = land_cover.resolve(SUPPORTED_YEARS[-1] if year is None else year)
        except MpcLandCoverError as err:
            raise _observation_error(err) from err
        response.headers["Cache-Control"] = "public, max-age=300"
        return {
            "year": resolved.year,
            "collection": resolved.collection,
            "item_ids": list(resolved.item_ids),
            "tile_urls": list(resolved.tile_templates),
            "bounds": list(resolved.bounds),
            "attribution": resolved.attribution,
        }

    @app.get("/api/places")
    def get_places() -> list[dict[str, Any]]:
        return [place.as_dict() for place in places.places]

    @app.get("/api/places/boundaries")
    def get_boundaries(level: Literal["province", "district"] = Query(...)) -> dict[str, Any]:
        if level not in places.boundaries:
            raise _error(404, f"No {level} boundaries are loaded", "no-data")
        return places.boundaries[level]

    @app.get("/api/tiles/{layer_id}/{z}/{x}/{y}")
    def get_tile(layer_id: str, z: int, x: int, y: int, year: int | None = None) -> Response:
        layer = layers.get(layer_id)
        if layer is None or layer.kind in ("boundary", "geojson"):
            raise _error(404, f"Unknown tile layer '{layer_id}'", "not-found")
        if not 0 <= z <= MAX_ZOOM or not 0 <= x < 2**z or not 0 <= y < 2**z:
            raise _error(422, f"Tile {z}/{x}/{y} does not exist", "bad-tile")
        if sections[layer.section_id].status == "coming-soon":
            raise _error(404, f"Layer '{layer_id}' is coming soon", "coming-soon")
        provider = tiles.get(layer_id)
        if layer.status != "ready" or provider is None:
            raise _error(404, f"Layer '{layer_id}' has no data loaded", "no-data")
        if year is not None and layer.years and not layer.years.first <= year <= layer.years.last:
            raise _error(
                422,
                f"Year {year} is outside {layer.years.first}-{layer.years.last}",
                "year-out-of-range",
            )
        result = provider(z, x, y, year)
        if result is None:
            return Response(status_code=204)
        content, media_type = result
        return Response(content=content, media_type=media_type)

    @app.get("/api/layers/{layer_id}/geojson")
    def get_layer_geojson(layer_id: str) -> dict[str, Any]:
        layer = layers.get(layer_id)
        if layer is None or layer.kind != "geojson":
            raise _error(404, f"Unknown shape layer '{layer_id}'", "not-found")
        if sections[layer.section_id].status == "coming-soon":
            raise _error(404, f"Layer '{layer_id}' is coming soon", "coming-soon")
        provider = geojson.get(layer_id)
        if layer.status != "ready" or provider is None:
            raise _error(404, f"Layer '{layer_id}' has no data loaded", "no-data")
        return provider()

    @app.get("/api/sections/{section_id}/data")
    def get_section_data(
        section_id: str, place: str = COUNTRY_ID, year: int | None = None
    ) -> dict[str, Any]:
        section = sections.get(section_id)
        if section is None:
            raise _error(404, f"Unknown section '{section_id}'", "not-found")
        target = places.by_id.get(place)
        if target is None:
            raise _error(404, f"Unknown place '{place}'", "not-found")
        if section.status == "coming-soon":
            raise _error(404, f"Section '{section_id}' is coming soon", "coming-soon")
        provider = section_data.get(section_id)
        if section.status == "no-data" or provider is None:
            raise _error(404, f"Section '{section_id}' has no data loaded", "no-data")
        if section.years is None:
            year = None
        elif year is None:
            year = section.years.last
        elif not section.years.first <= year <= section.years.last:
            raise _error(
                422,
                f"Year {year} is outside {section.years.first}-{section.years.last}",
                "year-out-of-range",
            )
        # A section without figures at this level uses the nearest level above that it does have:
        # a district gets its province's figures if there are any, otherwise the country's.
        while target.level not in section.place_levels and target.parent_id in places.by_id:
            target = places.by_id[target.parent_id]
        if target.level not in section.place_levels:
            target = places.by_id[COUNTRY_ID]
        body = provider(target, year)
        return {
            "section_id": section_id,
            "place_id": target.id,
            "level_used": target.level,
            "year": year,
            "figures": body.get("figures", []),
            "charts": body.get("charts", []),
            "notes": body.get("notes", []),
            "insights": body.get("insights", []),
        }

    return app

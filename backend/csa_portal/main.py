"""The portal's HTTP API. Start with: uvicorn csa_portal.main:create_app --factory"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, Any, Literal

from .geoenv import use_bundled_proj

use_bundled_proj()  # before anything imports rasterio

from fastapi import FastAPI, HTTPException, Query, Response  # noqa: E402
from titiler.core.dependencies import parse_color  # noqa: E402
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers  # noqa: E402
from titiler.core.factory import TilerFactory  # noqa: E402

from .catalogue import Layer, load_catalogue  # noqa: E402
from .places import COUNTRY_ID, BoundaryError, Place, load_places, no_places  # noqa: E402
from .sections import GeoJsonProvider, SectionDataProvider, build_providers  # noqa: E402
from .settings import Settings  # noqa: E402

TileProvider = Callable[[int, int, int, int | None], tuple[bytes, str] | None]

MAX_ZOOM = 24
COG_PREFIX = "/api/cog"

logger = logging.getLogger("uvicorn.error")


def _error(status: int, message: str, reason: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"message": message, "reason": reason})


def create_app(
    settings: Settings | None = None,
    section_providers: Mapping[str, SectionDataProvider] | None = None,
    tile_providers: Mapping[str, TileProvider] | None = None,
    geojson_providers: Mapping[str, GeoJsonProvider] | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
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

    app = FastAPI(title="CSA Portal")

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
        if layer.kind == "raster" and layer.source:
            if raster_file(layer) is None:
                body["status"] = "no-data"
            elif layer.status == "ready":
                body["tile_url"] = f"{COG_PREFIX}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?layer={layer.id}"
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

    cog = TilerFactory(router_prefix=COG_PREFIX, path_dependency=cog_path, colormap_dependency=cog_colormap)
    app.include_router(cog.router, prefix=COG_PREFIX, tags=["Land cover"])
    add_exception_handlers(app, DEFAULT_STATUS_CODES)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "boundaries_loaded": places.loaded,
            "boundaries_error": boundaries_error,
            "layers": {
                layer.id: places.loaded
                if layer.kind == "boundary"
                else layer.id in tiles or layer.id in geojson or raster_file(layer) is not None
                for layer in catalogue.layers
            },
        }

    @app.get("/api/catalogue")
    def get_catalogue() -> dict[str, Any]:
        return {
            "basemap_style_url": settings.basemap_style_url,
            "sections": [section.model_dump() for section in catalogue.sections],
            "layers": [served(layer) for layer in catalogue.layers],
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
        }

    return app

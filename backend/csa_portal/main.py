"""The portal's HTTP API. Start with: uvicorn csa_portal.main:create_app --factory"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Response

from .catalogue import load_catalogue
from .places import COUNTRY_ID, Place, load_places
from .settings import Settings

SectionDataProvider = Callable[[Place, int | None], dict[str, Any]]
TileProvider = Callable[[int, int, int, int | None], tuple[bytes, str] | None]

MAX_ZOOM = 24


def _error(status: int, message: str, reason: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"message": message, "reason": reason})


def create_app(
    settings: Settings | None = None,
    section_providers: Mapping[str, SectionDataProvider] | None = None,
    tile_providers: Mapping[str, TileProvider] | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    catalogue = load_catalogue(settings.catalogue_path)
    places = load_places(settings.boundaries_dir)
    section_data = dict(section_providers or {})
    tiles = dict(tile_providers or {})
    sections = {section.id: section for section in catalogue.sections}
    layers = {layer.id: layer for layer in catalogue.layers}

    app = FastAPI(title="CSA Portal")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "boundaries_loaded": places.loaded,
            "layers": {
                layer.id: places.loaded if layer.kind == "boundary" else layer.id in tiles
                for layer in catalogue.layers
            },
        }

    @app.get("/api/catalogue")
    def get_catalogue() -> dict[str, Any]:
        return {"basemap_style_url": settings.basemap_style_url, **catalogue.model_dump()}

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
        if layer is None or layer.kind == "boundary":
            raise _error(404, f"Unknown layer '{layer_id}'", "not-found")
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
        }

    return app

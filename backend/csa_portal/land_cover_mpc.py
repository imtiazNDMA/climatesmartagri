"""Resolve annual Pakistan land-classification tiles from Microsoft Planetary Computer."""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlencode

import httpx
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.errors import GEOSException
from shapely.ops import unary_union

STAC_API = "https://planetarycomputer.microsoft.com/api/stac/v1"
TILE_API = "https://planetarycomputer.microsoft.com/api/data/v1"
COLLECTION = "io-lulc-annual-v02"
VERSION = "v02"
SUPPORTED_YEARS = tuple(range(2017, 2024))
ATTRIBUTION = "Esri / Impact Observatory / Microsoft Planetary Computer"
# MPC hands out search ids like "pc1.1793161178.6ea9c1a9…"; anything else is not put into a URL.
_SEARCH_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")


class MpcLandCoverError(RuntimeError):
    """A stable error callers can translate without depending on httpx internals."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def pakistan_geometry(boundaries_dir: Path) -> dict[str, Any]:
    """The country's outline from the prepared province boundaries, as GeoJSON.

    The prepared boundaries carry imperfect topology, so the union is repaired before it is used
    to ask the catalogue what covers the country.
    """
    path = Path(boundaries_dir) / "provinces.geojson"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MpcLandCoverError(f"cannot read {path}", "invalid-boundaries") from error
    features = document.get("features") if isinstance(document, dict) else None
    if not isinstance(features, list) or not features:
        raise MpcLandCoverError(f"{path} has no features", "invalid-boundaries")
    try:
        geometries = [make_valid(shape(feature["geometry"])) for feature in features]
        country = make_valid(unary_union(geometries))
    except (KeyError, TypeError, ValueError, GEOSException) as error:
        raise MpcLandCoverError(f"{path} has invalid geometry", "invalid-boundaries") from error
    if country.is_empty or not country.is_valid:
        raise MpcLandCoverError(f"{path} does not describe a valid country", "invalid-boundaries")
    return mapping(country)


@dataclass(frozen=True)
class ResolvedLandCover:
    year: int
    collection: str
    version: str
    item_ids: tuple[str, ...]
    # The MPC mosaic registered over exactly item_ids; every tile URL for the year is built from it.
    search_id: str
    bounds: tuple[float, float, float, float]
    attribution: str
    expires_at: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def mosaic_tile_url(search_id: str, colormap: Mapping[int, str]) -> str:
    """The tile URL template for a year's mosaic, drawing each class in colormap in its #rrggbb colour.

    Classes left out of the colormap are drawn transparent, so one entry draws one class. The
    placeholders stay literal for the map; only the query is encoded.
    """
    colours = {
        str(code): [int(colour[i:i + 2], 16) for i in (1, 3, 5)] + [255]
        for code, colour in sorted(colormap.items())
    }
    query = urlencode({
        "collection": COLLECTION,
        "assets": "data",
        "colormap": json.dumps(colours, separators=(",", ":")),
    })
    return f"{TILE_API}/mosaic/{search_id}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}@1x.png?{query}"


class LandCoverResolver(Protocol):
    """What the portal needs from an annual land-classification source."""

    def resolve(self, year: int) -> ResolvedLandCover: ...


class MpcLandCoverResolver:
    """Resolve and briefly cache the complete set of annual MPC item tile templates."""

    def __init__(
        self,
        client: httpx.Client,
        pakistan_geometry: Mapping[str, Any],
        *,
        now: Callable[[], float] = time.monotonic,
        cache_ttl_seconds: float = 30 * 60,
    ):
        if cache_ttl_seconds <= 0:
            raise ValueError("cache_ttl_seconds must be positive")
        self._client = client
        self._geometry = pakistan_geometry
        self._aoi = shape(pakistan_geometry)
        if self._aoi.is_empty or not self._aoi.is_valid:
            raise ValueError("Pakistan geometry must be non-empty and valid")
        self._now = now
        self._ttl = cache_ttl_seconds
        self._cache: dict[int, ResolvedLandCover] = {}
        self._lock = threading.Lock()
        self._year_locks = {year: threading.Lock() for year in SUPPORTED_YEARS}

    def invalidate(self, year: int | None = None) -> None:
        with self._lock:
            if year is None:
                self._cache.clear()
            else:
                self._cache.pop(year, None)

    def resolve(self, year: int) -> ResolvedLandCover:
        if year not in SUPPORTED_YEARS:
            raise MpcLandCoverError(
                f"unsupported year {year}; choose {SUPPORTED_YEARS[0]}-{SUPPORTED_YEARS[-1]}",
                "year-out-of-range",
            )
        with self._lock:
            cached = self._cache.get(year)
            if cached is not None and cached.expires_at > self._now():
                return cached
        with self._year_locks[year]:
            with self._lock:
                cached = self._cache.get(year)
                if cached is not None and cached.expires_at > self._now():
                    return cached
            resolved = self._resolve(year)
            with self._lock:
                self._cache[year] = resolved
            return resolved

    def _json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, url, **kwargs)
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as error:
            raise MpcLandCoverError("Microsoft Planetary Computer timed out", "upstream-timeout") from error
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if 400 <= status < 500 and status != 429:
                raise MpcLandCoverError(
                    f"Microsoft Planetary Computer rejected the request ({status})", "upstream-rejected"
                ) from error
            raise MpcLandCoverError(
                f"Microsoft Planetary Computer is unavailable ({status})", "upstream-unavailable"
            ) from error
        except httpx.HTTPError as error:
            raise MpcLandCoverError("Microsoft Planetary Computer is unavailable", "upstream-unavailable") from error
        except ValueError as error:
            raise MpcLandCoverError("Microsoft Planetary Computer returned invalid JSON", "invalid-upstream-response") from error
        if not isinstance(body, dict):
            raise MpcLandCoverError("Microsoft Planetary Computer returned an invalid object", "invalid-upstream-response")
        return body

    def _items(self, year: int) -> list[dict[str, Any]]:
        search_body = {
            "collections": [COLLECTION],
            "intersects": self._geometry,
            "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
            "limit": 100,
        }
        body = self._json("POST", f"{STAC_API}/search", json=search_body, timeout=20)
        features: list[Any] = []
        while True:
            page = body.get("features")
            if not isinstance(page, list):
                raise MpcLandCoverError("STAC response has no feature list", "invalid-upstream-response")
            features.extend(page)
            links = body.get("links", [])
            if not isinstance(links, list):
                raise MpcLandCoverError("STAC response has invalid links", "invalid-upstream-response")
            next_link = next((link for link in links if isinstance(link, dict) and link.get("rel") == "next"), None)
            if next_link is None:
                break
            href = next_link.get("href")
            if not isinstance(href, str) or not href.startswith(STAC_API):
                raise MpcLandCoverError("STAC response has an invalid next link", "invalid-upstream-response")
            method = str(next_link.get("method", "GET")).upper()
            if method not in {"GET", "POST"}:
                raise MpcLandCoverError("STAC response has an invalid next method", "invalid-upstream-response")
            kwargs = {"json": next_link.get("body", search_body)} if method == "POST" else {}
            body = self._json(method, href, timeout=20, **kwargs)
        if not features:
            raise MpcLandCoverError(f"MPC has no land-classification items for {year}", "no-data")
        ids: set[str] = set()
        geometries = []
        valid: list[dict[str, Any]] = []
        for feature in features:
            if not isinstance(feature, dict) or not isinstance(feature.get("id"), str):
                raise MpcLandCoverError("STAC response contains an invalid item", "invalid-upstream-response")
            item_id = feature["id"]
            if item_id in ids:
                raise MpcLandCoverError(f"duplicate item {item_id}", "invalid-source")
            ids.add(item_id)
            properties = feature.get("properties")
            timestamp = properties.get("start_datetime") if isinstance(properties, dict) else None
            timestamp = timestamp or (properties.get("datetime") if isinstance(properties, dict) else None)
            if not isinstance(timestamp, str):
                raise MpcLandCoverError(f"item {item_id} has no observation time", "invalid-source")
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                item_year = int(timestamp[:4])
            except ValueError as error:
                raise MpcLandCoverError(f"item {item_id} has invalid observation time", "invalid-source") from error
            if item_year != year:
                continue
            assets = feature.get("assets")
            data_asset = assets.get("data") if isinstance(assets, dict) else None
            if not isinstance(data_asset, dict) or not isinstance(data_asset.get("href"), str):
                raise MpcLandCoverError(f"item {item_id} has no data asset", "invalid-source")
            try:
                geometry = shape(feature["geometry"])
            except (KeyError, TypeError, ValueError, GEOSException) as error:
                raise MpcLandCoverError(f"item {item_id} has invalid geometry", "invalid-source") from error
            if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
                raise MpcLandCoverError(f"item {item_id} has invalid geometry", "invalid-source")
            geometries.append(geometry)
            valid.append(feature)
        if not valid:
            raise MpcLandCoverError(f"MPC has no land-classification items for {year}", "no-data")
        try:
            uncovered = self._aoi.difference(unary_union(geometries))
        except GEOSException as error:
            raise MpcLandCoverError("source geometries cannot be combined", "invalid-source") from error
        if not uncovered.is_empty and uncovered.area / self._aoi.area > 1e-6:
            raise MpcLandCoverError(f"items for {year} do not cover Pakistan", "incomplete-source")
        return sorted(valid, key=lambda feature: feature["id"])

    def _register_mosaic(self, item_ids: tuple[str, ...]) -> str:
        """Register one MPC mosaic over exactly these items, so a tile draws whichever covers it.

        The ids, not a date range, select the items: a year's range also touches the previous
        year's items, which end on its first instant.
        """
        body = self._json(
            "POST",
            f"{TILE_API}/mosaic/register",
            json={
                "collections": [COLLECTION],
                "filter-lang": "cql2-json",
                "filter": {"op": "in", "args": [{"property": "id"}, list(item_ids)]},
            },
            timeout=20,
        )
        search_id = body.get("searchid")
        if not isinstance(search_id, str) or not _SEARCH_ID.fullmatch(search_id):
            raise MpcLandCoverError("mosaic registration returned no usable search id", "invalid-upstream-response")
        return search_id

    def _resolve(self, year: int) -> ResolvedLandCover:
        items = self._items(year)
        item_ids = tuple(item["id"] for item in items)
        search_id = self._register_mosaic(item_ids)
        bounds = tuple(float(value) for value in self._aoi.bounds)
        return ResolvedLandCover(
            year=year,
            collection=COLLECTION,
            version=VERSION,
            item_ids=item_ids,
            search_id=search_id,
            bounds=bounds,  # type: ignore[arg-type]
            attribution=ATTRIBUTION,
            expires_at=self._now() + self._ttl,
        )

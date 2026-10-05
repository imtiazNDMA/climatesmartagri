# CSA Portal Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the map-first Climate Smart Agriculture portal shell: a localhost FastAPI + React app with the full layout, layer catalogue, place selection, layer stacking, time slider and shareable URL state, but no real data layers yet.

**Architecture:** A FastAPI backend owns one catalogue file describing every section and layer, a places index built from boundary GeoJSON, and tile and section-data routes that are seams for later sub-projects. A React frontend reads the catalogue at start-up and builds the rail, panels, legend and time slider from it. One Zustand store holds the view (open section, active layers, place, year) and is mirrored to the URL.

**Tech Stack:** Python 3.13, uv, FastAPI, Pydantic v2, pytest. Node 24, Vite, React, TypeScript, MapLibre GL JS, Zustand, lucide-react, Vitest, Playwright. Windows 11; commands below work in Git Bash or PowerShell unless marked.

**Spec:** `docs/superpowers/specs/2026-10-05-csa-portal-shell-design.md`

## Global Constraints

- All backend routes are under `/api`.
- Place identifiers are the boundary dataset's own administrative codes. `PK` identifies the whole country.
- Section ids, in rail order: `land-cover`, `irrigation`, `emissions`, `water-balance`, `food-security`, `climate-calendar`, `hazards`, `exposure`. The last two have status `coming-soon`; the rest `no-data`.
- Section status is one of `ready`, `no-data`, `coming-soon`. Layer status is one of `ready`, `no-data`. Layer kind is one of `raster`, `vector`, `boundary`.
- Boundary layers `provinces` and `districts` are always on and never appear in a section panel or the active layers list.
- Unknown `layer_id`, `section_id` or `place` returns 404 with a message naming what was not found. A `year` outside the range returns 422. `no-data` and `coming-soon` return 404 with that `reason`.
- URL parameters: `section`, `layers` (`id:opacity` comma-separated, top first), `hidden`, `place`, `year`. Unknown values are dropped with a notice.
- Charts and figures follow the open section, never the stack of active layers.
- The section panel covers the map as a full-height sheet below 900 pixels wide.
- User-facing copy, verbatim: "Data not loaded yet", "Coming soon", "National figures only".
- `npm run dev` at the repo root starts both halves and opens the browser.
- Tests are written before the code they cover.
- The shell ships no real data layers and no charts. Visual polish is a later design pass; styling here is functional only.
- The boundary dataset's licence and border depiction must be confirmed by the project owner before real boundary files are committed (Task 5).

## Review Focus

1. **Boundary files missing or malformed** — the backend still starts, `/api/health` reports `boundaries_loaded: false`, and the portal loads with a notice instead of a blank page. Tests in Task 2 (`test_missing_directory_is_not_fatal`), Task 3 (`test_boundaries_missing_returns_no_data`) and Task 9 (`shows a notice when boundaries are not loaded`).
2. **Catalogue ids that break the URL format** — an id containing `:`, `,`, spaces or capitals is rejected when the catalogue loads, with the id named. Test in Task 1 (`test_unsafe_ids_rejected`).
3. **Hand-edited URLs** — a duplicate layer, opacity `abc` or `5`, year `2015.5`, or an empty `layers=` never crash the page; each bad value is dropped or defaulted. Tests in Task 8 (`handles garbage values without throwing`).
4. **Place search input as typed by people** — different case, leading or trailing spaces, and an empty query all behave sensibly. Tests in Task 7 (`searchPlaces`).
5. **Tile coordinates out of range** — negative values, `x` or `y` beyond `2^z`, or absurd zoom return 422 and never reach a tile provider. Test in Task 3 (`test_tile_coordinates_out_of_range`).

---

## File Structure

```
package.json                      root dev and test commands
backend/
  catalogue.json                  the real catalogue (8 sections)
  boundaries/                     provinces.geojson, districts.geojson (Task 5)
  csa_portal/
    __init__.py
    settings.py                   paths and basemap URL, env overrides
    catalogue.py                  catalogue models, loading, validation
    places.py                     place index built from boundary GeoJSON
    main.py                       create_app() and all routes
  scripts/prepare_boundaries.py   one-time boundary normaliser
  tests/
    conftest.py
    fixtures/test_catalogue.json
    fixtures/boundaries/{provinces,districts}.geojson
    test_catalogue.py  test_places.py  test_api.py
    test_real_catalogue.py  test_prepare_boundaries.py
frontend/
  vite.config.ts  playwright.config.ts
  src/
    main.tsx  App.tsx  styles.css
    api/types.ts  api/client.ts
    state/viewState.ts  state/uiState.ts  state/selectors.ts
    state/urlState.ts  state/useUrlSync.ts
    data/usePortalData.ts  data/useSectionData.ts  data/useLayerProbes.ts
    components/BackendDown.tsx  Notices.tsx  IconRail.tsx  SectionPanel.tsx
    components/AboutDialog.tsx  MapView.tsx  ActiveLayers.tsx  Legend.tsx
    components/TimeSlider.tsx  PlaceSearch.tsx  Breadcrumb.tsx
  e2e/helpers.ts  e2e/*.spec.ts
```

---

### Task 0: Working branch

- [ ] **Step 1: Create the feature branch from the spec branch**

```bash
git switch docs/csa-portal-shell-spec
git switch -c feat/portal-shell
```

- [ ] **Step 2: Extend `.gitignore`**

Append to `.gitignore`:

```
# Node
node_modules/
frontend/dist/
frontend/test-results/
frontend/playwright-report/
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore node and playwright output"
```

---

### Task 1: Catalogue models and validation

**Files:**
- Modify: `pyproject.toml`
- Create: `backend/csa_portal/__init__.py` (empty)
- Create: `backend/csa_portal/catalogue.py`
- Test: `backend/tests/test_catalogue.py`

**Interfaces:**
- Produces: `Catalogue`, `Section`, `Layer`, `YearRange`, `CatalogueError`, `load_catalogue(path: Path) -> Catalogue`. `Section` fields: `id, title, icon, order, status, summary, place_levels, years`. `Layer` fields: `id, section_id, title, kind, status, legend, years, default_opacity`. `summary` is an addition to the spec's table: the one line shown under "Coming soon".

- [ ] **Step 1: Add dependencies and pytest config**

```bash
uv add fastapi "uvicorn[standard]"
uv add --dev pytest httpx
```

Append to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["backend"]
testpaths = ["backend/tests"]
```

Create empty `backend/csa_portal/__init__.py`.

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_catalogue.py`:

```python
import copy
import json

import pytest

from csa_portal.catalogue import CatalogueError, load_catalogue

VALID = {
    "sections": [
        {
            "id": "s1",
            "title": "S1",
            "icon": "trees",
            "order": 1,
            "status": "ready",
            "place_levels": ["national"],
        }
    ],
    "layers": [
        {
            "id": "l1",
            "section_id": "s1",
            "title": "L1",
            "kind": "raster",
            "status": "ready",
            "legend": {
                "type": "classes",
                "items": [{"colour": "#000000", "label": "x"}],
            },
        }
    ],
}


def _load(tmp_path, data):
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return load_catalogue(path)


def _valid():
    return copy.deepcopy(VALID)


def test_valid_catalogue_loads(tmp_path):
    catalogue = _load(tmp_path, _valid())
    assert catalogue.sections[0].id == "s1"
    assert catalogue.sections[0].years is None
    assert catalogue.sections[0].summary == ""
    assert catalogue.layers[0].default_opacity == 1.0


def test_duplicate_section_ids_rejected(tmp_path):
    data = _valid()
    data["sections"].append(copy.deepcopy(data["sections"][0]))
    with pytest.raises(CatalogueError, match="s1"):
        _load(tmp_path, data)


def test_duplicate_layer_ids_rejected(tmp_path):
    data = _valid()
    data["layers"].append(copy.deepcopy(data["layers"][0]))
    with pytest.raises(CatalogueError, match="l1"):
        _load(tmp_path, data)


def test_layer_with_unknown_section_rejected(tmp_path):
    data = _valid()
    data["layers"][0]["section_id"] = "nope"
    with pytest.raises(CatalogueError, match="nope"):
        _load(tmp_path, data)


@pytest.mark.parametrize("bad_id", ["a:b", "a,b", "A b", "Upper", ""])
def test_unsafe_ids_rejected(tmp_path, bad_id):
    data = _valid()
    data["layers"][0]["id"] = bad_id
    with pytest.raises(CatalogueError):
        _load(tmp_path, data)


def test_status_outside_allowed_set_rejected(tmp_path):
    data = _valid()
    data["sections"][0]["status"] = "soon"
    with pytest.raises(CatalogueError):
        _load(tmp_path, data)


def test_reversed_year_range_rejected(tmp_path):
    data = _valid()
    data["sections"][0]["years"] = {"first": 2021, "last": 1994}
    with pytest.raises(CatalogueError):
        _load(tmp_path, data)


def test_non_boundary_layer_needs_legend_and_section(tmp_path):
    data = _valid()
    del data["layers"][0]["legend"]
    with pytest.raises(CatalogueError, match="l1"):
        _load(tmp_path, data)


def test_boundary_layer_needs_neither(tmp_path):
    data = _valid()
    data["layers"].append(
        {"id": "provinces", "title": "Provinces", "kind": "boundary", "status": "ready"}
    )
    catalogue = _load(tmp_path, data)
    assert catalogue.layers[1].section_id is None


def test_missing_file_gives_clear_error(tmp_path):
    with pytest.raises(CatalogueError, match="not found"):
        load_catalogue(tmp_path / "absent.json")


def test_invalid_json_gives_clear_error(tmp_path):
    path = tmp_path / "catalogue.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogueError, match="not valid JSON"):
        load_catalogue(path)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest backend/tests/test_catalogue.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'csa_portal.catalogue'`

- [ ] **Step 4: Implement**

`backend/csa_portal/catalogue.py`:

```python
"""The layer catalogue: every section and layer the portal knows about."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

SectionStatus = Literal["ready", "no-data", "coming-soon"]
LayerStatus = Literal["ready", "no-data"]
LayerKind = Literal["raster", "vector", "boundary"]
PlaceLevel = Literal["national", "province", "district"]

# Ids appear in the URL as `id:opacity,id:opacity`, so they must stay URL-safe.
Identifier = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]


class CatalogueError(ValueError):
    """The catalogue file is missing or invalid."""


class YearRange(BaseModel):
    first: int
    last: int

    @model_validator(mode="after")
    def _ordered(self) -> YearRange:
        if self.first > self.last:
            raise ValueError(f"year range {self.first}-{self.last} is reversed")
        return self


class LegendItem(BaseModel):
    colour: str
    label: str


class ClassLegend(BaseModel):
    type: Literal["classes"]
    items: list[LegendItem] = Field(min_length=1)


class RampLegend(BaseModel):
    type: Literal["ramp"]
    colours: list[str] = Field(min_length=2)
    min: float
    max: float
    unit: str = ""


Legend = Annotated[ClassLegend | RampLegend, Field(discriminator="type")]


class Section(BaseModel):
    id: Identifier
    title: str
    icon: str
    order: int
    status: SectionStatus
    summary: str = ""
    place_levels: list[PlaceLevel] = Field(min_length=1)
    years: YearRange | None = None


class Layer(BaseModel):
    id: Identifier
    section_id: str | None = None
    title: str
    kind: LayerKind
    status: LayerStatus
    legend: Legend | None = None
    years: YearRange | None = None
    default_opacity: float = Field(default=1.0, ge=0, le=1)


class Catalogue(BaseModel):
    sections: list[Section]
    layers: list[Layer]

    @model_validator(mode="after")
    def _consistent(self) -> Catalogue:
        section_ids = [s.id for s in self.sections]
        for section_id in section_ids:
            if section_ids.count(section_id) > 1:
                raise ValueError(f"duplicate section id '{section_id}'")
        layer_ids = [layer.id for layer in self.layers]
        for layer in self.layers:
            if layer_ids.count(layer.id) > 1:
                raise ValueError(f"duplicate layer id '{layer.id}'")
            if layer.kind == "boundary":
                continue
            if layer.section_id not in section_ids:
                raise ValueError(
                    f"layer '{layer.id}' names unknown section '{layer.section_id}'"
                )
            if layer.legend is None:
                raise ValueError(f"layer '{layer.id}' has no legend")
        return self


def load_catalogue(path: Path) -> Catalogue:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise CatalogueError(f"Catalogue file not found: {path}") from err
    except json.JSONDecodeError as err:
        raise CatalogueError(f"Catalogue file is not valid JSON: {path}: {err}") from err
    try:
        return Catalogue.model_validate(raw)
    except ValidationError as err:
        raise CatalogueError(f"Catalogue file is invalid: {path}: {err}") from err
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest backend/tests/test_catalogue.py -v`
Expected: 15 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock backend/csa_portal backend/tests/test_catalogue.py
git commit -m "feat(backend): catalogue models and validation"
```

---

### Task 2: Places index

**Files:**
- Create: `backend/csa_portal/places.py`
- Create: `backend/tests/fixtures/boundaries/provinces.geojson`
- Create: `backend/tests/fixtures/boundaries/districts.geojson`
- Test: `backend/tests/test_places.py`

**Interfaces:**
- Produces: `COUNTRY_ID = "PK"`, `Place(id, name, level, parent_id, bbox)` with `as_dict()`, `PlaceIndex(places, boundaries, loaded)` with `by_id`, `BoundaryError`, `load_places(boundaries_dir: Path) -> PlaceIndex`.
- Boundary file contract (also what Task 5 must produce): a GeoJSON FeatureCollection where every feature has properties `id` and `name`, and districts also have `parent_id` holding a province `id`.

- [ ] **Step 1: Create the fixture boundaries**

`backend/tests/fixtures/boundaries/provinces.geojson`:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "id": "PK1", "name": "Alpha", "parent_id": "PK" },
      "geometry": { "type": "Polygon", "coordinates": [[[66, 26], [70, 26], [70, 30], [66, 30], [66, 26]]] }
    },
    {
      "type": "Feature",
      "properties": { "id": "PK2", "name": "Beta", "parent_id": "PK" },
      "geometry": { "type": "Polygon", "coordinates": [[[70, 26], [74, 26], [74, 30], [70, 30], [70, 26]]] }
    }
  ]
}
```

`backend/tests/fixtures/boundaries/districts.geojson`:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "id": "PK101", "name": "District One", "parent_id": "PK1" },
      "geometry": { "type": "Polygon", "coordinates": [[[66, 26], [68, 26], [68, 30], [66, 30], [66, 26]]] }
    },
    {
      "type": "Feature",
      "properties": { "id": "PK102", "name": "District Two", "parent_id": "PK1" },
      "geometry": { "type": "Polygon", "coordinates": [[[68, 26], [70, 26], [70, 30], [68, 30], [68, 26]]] }
    },
    {
      "type": "Feature",
      "properties": { "id": "PK201", "name": "District Three", "parent_id": "PK2" },
      "geometry": {
        "type": "MultiPolygon",
        "coordinates": [[[[70, 26], [74, 26], [74, 30], [70, 30], [70, 26]]]]
      }
    }
  ]
}
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_places.py`:

```python
import json
import shutil
from pathlib import Path

import pytest

from csa_portal.places import COUNTRY_ID, FALLBACK_BBOX, BoundaryError, load_places

FIXTURES = Path(__file__).parent / "fixtures" / "boundaries"


def test_loads_country_provinces_and_districts():
    index = load_places(FIXTURES)
    assert index.loaded is True
    assert [p.id for p in index.places] == ["PK", "PK1", "PK2", "PK101", "PK201", "PK102"]
    assert index.by_id["PK101"].parent_id == "PK1"
    assert index.by_id["PK1"].level == "province"
    assert index.by_id["PK1"].parent_id == COUNTRY_ID


def test_bbox_from_polygon_and_multipolygon():
    index = load_places(FIXTURES)
    assert index.by_id["PK101"].bbox == (66, 26, 68, 30)
    assert index.by_id["PK201"].bbox == (70, 26, 74, 30)


def test_country_bbox_is_union_of_provinces():
    index = load_places(FIXTURES)
    assert index.by_id["PK"].bbox == (66, 26, 74, 30)


def test_missing_directory_is_not_fatal(tmp_path):
    index = load_places(tmp_path / "absent")
    assert index.loaded is False
    assert [p.id for p in index.places] == ["PK"]
    assert index.by_id["PK"].bbox == FALLBACK_BBOX
    assert index.boundaries == {}


def test_one_missing_file_marks_not_loaded(tmp_path):
    shutil.copy(FIXTURES / "provinces.geojson", tmp_path / "provinces.geojson")
    index = load_places(tmp_path)
    assert index.loaded is False
    assert "province" in index.boundaries
    assert "district" not in index.boundaries


def test_feature_without_id_is_rejected(tmp_path):
    data = json.loads((FIXTURES / "provinces.geojson").read_text(encoding="utf-8"))
    del data["features"][0]["properties"]["id"]
    (tmp_path / "provinces.geojson").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BoundaryError, match="provinces.geojson"):
        load_places(tmp_path)


def test_duplicate_ids_are_rejected(tmp_path):
    data = json.loads((FIXTURES / "provinces.geojson").read_text(encoding="utf-8"))
    data["features"][1]["properties"]["id"] = "PK1"
    (tmp_path / "provinces.geojson").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BoundaryError, match="PK1"):
        load_places(tmp_path)


def test_district_with_unknown_province_is_rejected(tmp_path):
    shutil.copy(FIXTURES / "provinces.geojson", tmp_path / "provinces.geojson")
    data = json.loads((FIXTURES / "districts.geojson").read_text(encoding="utf-8"))
    data["features"][0]["properties"]["parent_id"] = "PK9"
    (tmp_path / "districts.geojson").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BoundaryError, match="PK9"):
        load_places(tmp_path)


def test_feature_without_geometry_is_skipped(tmp_path):
    data = json.loads((FIXTURES / "provinces.geojson").read_text(encoding="utf-8"))
    data["features"][1]["geometry"] = None
    (tmp_path / "provinces.geojson").write_text(json.dumps(data), encoding="utf-8")
    index = load_places(tmp_path)
    assert "PK2" not in index.by_id
    assert len(index.boundaries["province"]["features"]) == 1


def test_malformed_json_is_rejected(tmp_path):
    (tmp_path / "provinces.geojson").write_text("{oops", encoding="utf-8")
    with pytest.raises(BoundaryError, match="provinces.geojson"):
        load_places(tmp_path)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest backend/tests/test_places.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'csa_portal.places'`

- [ ] **Step 4: Implement**

`backend/csa_portal/places.py`:

```python
"""Provinces and districts, read from the boundary GeoJSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

COUNTRY_ID = "PK"
COUNTRY_NAME = "Pakistan"
# Used only when no province boundaries are loaded.
FALLBACK_BBOX = (60.87, 23.69, 77.84, 37.10)
LEVEL_FILES = {"province": "provinces.geojson", "district": "districts.geojson"}

Bbox = tuple[float, float, float, float]


class BoundaryError(ValueError):
    """A boundary file exists but cannot be used."""


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    level: str
    parent_id: str | None
    bbox: Bbox

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "parent_id": self.parent_id,
            "bbox": list(self.bbox),
        }


@dataclass
class PlaceIndex:
    places: list[Place]
    boundaries: dict[str, dict[str, Any]]
    loaded: bool
    by_id: dict[str, Place] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {place.id: place for place in self.places}


def _bbox(geometry: dict[str, Any]) -> Bbox:
    xs: list[float] = []
    ys: list[float] = []

    def walk(coords: Any) -> None:
        if coords and isinstance(coords[0], (int, float)):
            xs.append(coords[0])
            ys.append(coords[1])
        else:
            for item in coords:
                walk(item)

    walk(geometry.get("coordinates", []))
    if not xs:
        raise ValueError("geometry has no coordinates")
    return (min(xs), min(ys), max(xs), max(ys))


def _union(boxes: list[Bbox]) -> Bbox:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _read_level(path: Path, level: str) -> tuple[list[Place], dict[str, Any]]:
    try:
        collection = json.loads(path.read_text(encoding="utf-8"))
        features = collection["features"]
    except (json.JSONDecodeError, KeyError, TypeError) as err:
        raise BoundaryError(f"{path.name} is not a GeoJSON FeatureCollection: {err}") from err

    places: list[Place] = []
    kept: list[dict[str, Any]] = []
    for number, feature in enumerate(features):
        props = feature.get("properties") or {}
        if not props.get("id") or not props.get("name"):
            raise BoundaryError(f"{path.name}: feature {number} has no 'id' or 'name' property")
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            bbox = _bbox(geometry)
        except (ValueError, TypeError, IndexError) as err:
            raise BoundaryError(f"{path.name}: feature {number} has bad geometry: {err}") from err
        parent_id = COUNTRY_ID if level == "province" else props.get("parent_id")
        places.append(Place(str(props["id"]), str(props["name"]), level, parent_id, bbox))
        kept.append(feature)
    return places, {"type": "FeatureCollection", "features": kept}


def load_places(boundaries_dir: Path) -> PlaceIndex:
    boundaries_dir = Path(boundaries_dir)
    by_level: dict[str, list[Place]] = {}
    boundaries: dict[str, dict[str, Any]] = {}
    for level, filename in LEVEL_FILES.items():
        path = boundaries_dir / filename
        if path.is_file():
            by_level[level], boundaries[level] = _read_level(path, level)

    provinces = sorted(by_level.get("province", []), key=lambda p: p.name)
    districts = sorted(by_level.get("district", []), key=lambda p: p.name)

    seen: set[str] = {COUNTRY_ID}
    for place in [*provinces, *districts]:
        if place.id in seen:
            raise BoundaryError(f"duplicate place id '{place.id}'")
        seen.add(place.id)

    if "province" in by_level:
        province_ids = {p.id for p in provinces}
        for district in districts:
            if district.parent_id not in province_ids:
                raise BoundaryError(
                    f"district '{district.id}' names unknown province '{district.parent_id}'"
                )

    country_bbox = _union([p.bbox for p in provinces]) if provinces else FALLBACK_BBOX
    country = Place(COUNTRY_ID, COUNTRY_NAME, "national", None, country_bbox)
    return PlaceIndex(
        places=[country, *provinces, *districts],
        boundaries=boundaries,
        loaded=len(boundaries) == len(LEVEL_FILES),
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest backend/tests/test_places.py -v`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
git add backend/csa_portal/places.py backend/tests/test_places.py backend/tests/fixtures/boundaries
git commit -m "feat(backend): places index from boundary GeoJSON"
```

---

### Task 3: FastAPI app and routes

**Files:**
- Create: `backend/csa_portal/settings.py`
- Create: `backend/csa_portal/main.py`
- Create: `backend/tests/fixtures/test_catalogue.json`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `load_catalogue`, `load_places`, `Place`, `COUNTRY_ID`.
- Produces: `Settings(catalogue_path, boundaries_dir, basemap_style_url)` with `Settings.from_env()` reading `CSA_CATALOGUE_PATH`, `CSA_BOUNDARIES_DIR`, `CSA_BASEMAP_STYLE_URL`. `create_app(settings=None, section_providers=None, tile_providers=None) -> FastAPI`.
- Seams for later sub-projects: `SectionDataProvider = Callable[[Place, int | None], dict]` returning `{"figures": [...], "charts": [...]}`; `TileProvider = Callable[[int, int, int, int | None], tuple[bytes, str] | None]` taking `z, x, y, year` and returning `(content, media_type)` or `None` for an empty tile. The shell registers none.
- Error body shape: `{"detail": {"message": str, "reason": str}}` with `reason` one of `not-found`, `no-data`, `coming-soon`, `year-out-of-range`, `bad-tile`.
- The fixture catalogue is shared with the frontend end-to-end tests. Its names are relied on there: sections "Alpha section", "Beta section", "Later section", "Empty section"; layers "Fake yearly", "Fake static", "Fake empty".

- [ ] **Step 1: Create the fixture catalogue**

`backend/tests/fixtures/test_catalogue.json`:

```json
{
  "sections": [
    {
      "id": "alpha-section", "title": "Alpha section", "icon": "trees", "order": 1,
      "status": "ready", "place_levels": ["national", "province", "district"],
      "years": { "first": 2000, "last": 2010 }
    },
    {
      "id": "beta-section", "title": "Beta section", "icon": "droplets", "order": 2,
      "status": "ready", "place_levels": ["national"]
    },
    {
      "id": "later-section", "title": "Later section", "icon": "cloud-lightning", "order": 3,
      "status": "coming-soon", "summary": "Will show things later.",
      "place_levels": ["national"]
    },
    {
      "id": "empty-section", "title": "Empty section", "icon": "wheat", "order": 4,
      "status": "no-data", "place_levels": ["national"]
    }
  ],
  "layers": [
    { "id": "provinces", "title": "Provinces", "kind": "boundary", "status": "ready" },
    { "id": "districts", "title": "Districts", "kind": "boundary", "status": "ready" },
    {
      "id": "fake-yearly", "section_id": "alpha-section", "title": "Fake yearly",
      "kind": "raster", "status": "ready", "default_opacity": 0.8,
      "years": { "first": 2000, "last": 2010 },
      "legend": { "type": "classes", "items": [{ "colour": "#2e7d32", "label": "Yearly class" }] }
    },
    {
      "id": "fake-static", "section_id": "beta-section", "title": "Fake static",
      "kind": "raster", "status": "ready",
      "legend": { "type": "ramp", "colours": ["#ffffff", "#1565c0"], "min": 0, "max": 100, "unit": "%" }
    },
    {
      "id": "fake-empty", "section_id": "empty-section", "title": "Fake empty",
      "kind": "raster", "status": "no-data",
      "legend": { "type": "classes", "items": [{ "colour": "#9e9e9e", "label": "Empty class" }] }
    },
    {
      "id": "fake-later", "section_id": "later-section", "title": "Fake later",
      "kind": "raster", "status": "no-data",
      "legend": { "type": "classes", "items": [{ "colour": "#9e9e9e", "label": "Later class" }] }
    }
  ]
}
```

- [ ] **Step 2: Write conftest and the failing tests**

`backend/tests/conftest.py`:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from csa_portal.main import create_app
from csa_portal.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def fake_section(place, year):
    return {
        "figures": [{"label": "Place", "value": place.id, "unit": ""}],
        "charts": [],
    }


def fake_tile(z, x, y, year):
    return (f"tile-{z}-{x}-{y}-{year}".encode(), "image/png")


@pytest.fixture
def settings():
    return Settings(
        catalogue_path=FIXTURES / "test_catalogue.json",
        boundaries_dir=FIXTURES / "boundaries",
        basemap_style_url="https://example.test/style.json",
    )


@pytest.fixture
def client(settings):
    app = create_app(
        settings,
        section_providers={"alpha-section": fake_section, "beta-section": fake_section},
        tile_providers={"fake-yearly": fake_tile},
    )
    return TestClient(app)


@pytest.fixture
def bare_client(settings):
    """The app as the shell ships it: no providers registered."""
    return TestClient(create_app(settings))
```

`backend/tests/test_api.py`:

```python
from dataclasses import replace

from fastapi.testclient import TestClient

from csa_portal.main import create_app


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["boundaries_loaded"] is True
    assert body["layers"]["fake-yearly"] is True
    assert body["layers"]["fake-static"] is False
    assert body["layers"]["provinces"] is True


def test_catalogue(client):
    body = client.get("/api/catalogue").json()
    assert body["basemap_style_url"] == "https://example.test/style.json"
    assert [s["id"] for s in body["sections"]][:2] == ["alpha-section", "beta-section"]
    assert body["sections"][1]["years"] is None
    assert any(layer["id"] == "fake-yearly" for layer in body["layers"])


def test_places(client):
    body = client.get("/api/places").json()
    assert body[0] == {
        "id": "PK", "name": "Pakistan", "level": "national",
        "parent_id": None, "bbox": [66, 26, 74, 30],
    }
    assert {p["id"] for p in body} == {"PK", "PK1", "PK2", "PK101", "PK102", "PK201"}


def test_boundaries(client):
    body = client.get("/api/places/boundaries", params={"level": "district"}).json()
    assert body["type"] == "FeatureCollection"
    assert {f["properties"]["id"] for f in body["features"]} == {"PK101", "PK102", "PK201"}


def test_boundaries_bad_level(client):
    assert client.get("/api/places/boundaries", params={"level": "tehsil"}).status_code == 422


def test_boundaries_missing_returns_no_data(settings, tmp_path):
    app = create_app(replace(settings, boundaries_dir=tmp_path / "absent"))
    client = TestClient(app)
    assert client.get("/api/health").json()["boundaries_loaded"] is False
    response = client.get("/api/places/boundaries", params={"level": "province"})
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "no-data"
    assert [p["id"] for p in client.get("/api/places").json()] == ["PK"]


def test_tile_served_by_provider(client):
    response = client.get("/api/tiles/fake-yearly/3/5/2", params={"year": 2005})
    assert response.status_code == 200
    assert response.content == b"tile-3-5-2-2005"
    assert response.headers["content-type"] == "image/png"


def test_tile_unknown_layer(client):
    response = client.get("/api/tiles/ghost/0/0/0")
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "not-found"
    assert "ghost" in response.json()["detail"]["message"]


def test_tile_boundary_layer_is_not_a_tile_layer(client):
    assert client.get("/api/tiles/provinces/0/0/0").status_code == 404


def test_tile_no_data_and_coming_soon(client):
    no_data = client.get("/api/tiles/fake-empty/0/0/0")
    assert (no_data.status_code, no_data.json()["detail"]["reason"]) == (404, "no-data")
    soon = client.get("/api/tiles/fake-later/0/0/0")
    assert (soon.status_code, soon.json()["detail"]["reason"]) == (404, "coming-soon")


def test_tile_ready_layer_without_provider_is_no_data(client):
    response = client.get("/api/tiles/fake-static/0/0/0")
    assert (response.status_code, response.json()["detail"]["reason"]) == (404, "no-data")


def test_tile_year_out_of_range(client):
    response = client.get("/api/tiles/fake-yearly/0/0/0", params={"year": 1990})
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "year-out-of-range"


def test_tile_coordinates_out_of_range(client):
    for path in ("/api/tiles/fake-yearly/1/2/0", "/api/tiles/fake-yearly/1/0/2",
                 "/api/tiles/fake-yearly/-1/0/0", "/api/tiles/fake-yearly/40/0/0",
                 "/api/tiles/fake-yearly/2/-1/0"):
        response = client.get(path)
        assert response.status_code == 422, path
        assert response.json()["detail"]["reason"] == "bad-tile"


def test_tile_empty_from_provider_is_204(settings):
    app = create_app(settings, tile_providers={"fake-static": lambda z, x, y, year: None})
    assert TestClient(app).get("/api/tiles/fake-static/0/0/0").status_code == 204


def test_section_data_defaults(client):
    body = client.get("/api/sections/alpha-section/data").json()
    assert body["section_id"] == "alpha-section"
    assert body["place_id"] == "PK"
    assert body["level_used"] == "national"
    assert body["year"] == 2010
    assert body["figures"] == [{"label": "Place", "value": "PK", "unit": ""}]
    assert body["charts"] == []


def test_section_data_for_district_and_year(client):
    body = client.get(
        "/api/sections/alpha-section/data", params={"place": "PK101", "year": 2003}
    ).json()
    assert (body["place_id"], body["level_used"], body["year"]) == ("PK101", "district", 2003)


def test_section_data_falls_back_to_national(client):
    body = client.get("/api/sections/beta-section/data", params={"place": "PK101"}).json()
    assert body["place_id"] == "PK"
    assert body["level_used"] == "national"
    assert body["year"] is None


def test_section_data_unknown_section_and_place(client):
    section = client.get("/api/sections/ghost/data")
    assert section.status_code == 404
    assert "ghost" in section.json()["detail"]["message"]
    place = client.get("/api/sections/alpha-section/data", params={"place": "XX"})
    assert place.status_code == 404
    assert "XX" in place.json()["detail"]["message"]


def test_section_data_year_out_of_range(client):
    response = client.get("/api/sections/alpha-section/data", params={"year": 2011})
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "year-out-of-range"


def test_section_data_no_data_and_coming_soon(client):
    empty = client.get("/api/sections/empty-section/data")
    assert (empty.status_code, empty.json()["detail"]["reason"]) == (404, "no-data")
    later = client.get("/api/sections/later-section/data")
    assert (later.status_code, later.json()["detail"]["reason"]) == (404, "coming-soon")


def test_shell_has_no_providers(bare_client):
    data = bare_client.get("/api/sections/alpha-section/data")
    assert (data.status_code, data.json()["detail"]["reason"]) == (404, "no-data")
    tile = bare_client.get("/api/tiles/fake-yearly/0/0/0")
    assert (tile.status_code, tile.json()["detail"]["reason"]) == (404, "no-data")
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest backend/tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'csa_portal.main'`

- [ ] **Step 4: Implement settings**

`backend/csa_portal/settings.py`:

```python
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
        )
```

- [ ] **Step 5: Implement the app**

`backend/csa_portal/main.py`:

```python
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
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest -v`
Expected: all tests pass (46 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/csa_portal/settings.py backend/csa_portal/main.py backend/tests
git commit -m "feat(backend): API routes with provider seams"
```

---

### Task 4: The real catalogue

**Files:**
- Create: `backend/catalogue.json`
- Test: `backend/tests/test_real_catalogue.py`

**Interfaces:**
- Produces: the catalogue the portal ships with. Layer legends here are single-colour placeholders for layers whose data is not loaded; sub-project 2 replaces them when it wires the real data.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_real_catalogue.py`:

```python
from fastapi.testclient import TestClient

from csa_portal.catalogue import load_catalogue
from csa_portal.main import create_app
from csa_portal.settings import BACKEND_DIR, Settings

EXPECTED = [
    ("land-cover", "no-data"),
    ("irrigation", "no-data"),
    ("emissions", "no-data"),
    ("water-balance", "no-data"),
    ("food-security", "no-data"),
    ("climate-calendar", "no-data"),
    ("hazards", "coming-soon"),
    ("exposure", "coming-soon"),
]


def test_shipped_catalogue_is_valid_and_complete():
    catalogue = load_catalogue(BACKEND_DIR / "catalogue.json")
    ordered = sorted(catalogue.sections, key=lambda s: s.order)
    assert [(s.id, s.status) for s in ordered] == EXPECTED
    assert [s.order for s in ordered] == list(range(1, 9))
    assert all(s.summary for s in ordered if s.status == "coming-soon")
    boundary_ids = {layer.id for layer in catalogue.layers if layer.kind == "boundary"}
    assert boundary_ids == {"provinces", "districts"}
    assert all(
        layer.status == "no-data" for layer in catalogue.layers if layer.kind != "boundary"
    )


def test_shell_routes_return_no_data_or_coming_soon(tmp_path):
    settings = Settings(BACKEND_DIR / "catalogue.json", tmp_path, "https://example.test/s.json")
    client = TestClient(create_app(settings))
    for section_id, status in EXPECTED:
        response = client.get(f"/api/sections/{section_id}/data")
        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == status
    tile = client.get("/api/tiles/forest/0/0/0")
    assert tile.json()["detail"]["reason"] == "no-data"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/test_real_catalogue.py -v`
Expected: FAIL with `CatalogueError: Catalogue file not found`

- [ ] **Step 3: Write the catalogue**

`backend/catalogue.json`:

```json
{
  "sections": [
    {
      "id": "land-cover", "title": "Land cover", "icon": "trees", "order": 1,
      "status": "no-data", "place_levels": ["national", "province", "district"]
    },
    {
      "id": "irrigation", "title": "Irrigation practices", "icon": "droplets", "order": 2,
      "status": "no-data", "place_levels": ["national", "province", "district"]
    },
    {
      "id": "emissions", "title": "Greenhouse-gas emissions", "icon": "factory", "order": 3,
      "status": "no-data", "place_levels": ["national"],
      "years": { "first": 1994, "last": 2021 }
    },
    {
      "id": "water-balance", "title": "Crop water balance", "icon": "waves", "order": 4,
      "status": "no-data", "place_levels": ["national"]
    },
    {
      "id": "food-security", "title": "Food security projections", "icon": "wheat", "order": 5,
      "status": "no-data", "place_levels": ["national"]
    },
    {
      "id": "climate-calendar", "title": "Climate calendar", "icon": "calendar-days", "order": 6,
      "status": "no-data", "place_levels": ["national"]
    },
    {
      "id": "hazards", "title": "Hazards", "icon": "cloud-lightning", "order": 7,
      "status": "coming-soon",
      "summary": "Flood, drought and heatwave layers to overlay on cropland and irrigation.",
      "place_levels": ["national", "province", "district"]
    },
    {
      "id": "exposure", "title": "Exposure and vulnerability", "icon": "users", "order": 8,
      "status": "coming-soon",
      "summary": "Population and cropland at risk, with a district risk ranking.",
      "place_levels": ["national", "province", "district"]
    }
  ],
  "layers": [
    { "id": "provinces", "title": "Provinces", "kind": "boundary", "status": "ready" },
    { "id": "districts", "title": "Districts", "kind": "boundary", "status": "ready" },
    {
      "id": "forest", "section_id": "land-cover", "title": "Forest cover",
      "kind": "raster", "status": "no-data", "default_opacity": 0.8,
      "legend": { "type": "classes", "items": [{ "colour": "#2e7d32", "label": "Forest" }] }
    },
    {
      "id": "shrub-land", "section_id": "land-cover", "title": "Shrub land",
      "kind": "raster", "status": "no-data", "default_opacity": 0.8,
      "legend": { "type": "classes", "items": [{ "colour": "#9ccc65", "label": "Shrub land" }] }
    },
    {
      "id": "bare-land", "section_id": "land-cover", "title": "Bare land",
      "kind": "raster", "status": "no-data", "default_opacity": 0.8,
      "legend": { "type": "classes", "items": [{ "colour": "#bcaaa4", "label": "Bare land" }] }
    },
    {
      "id": "irrigated-rainfed", "section_id": "land-cover", "title": "Irrigated and rainfed cropland",
      "kind": "raster", "status": "no-data", "default_opacity": 0.8,
      "legend": { "type": "classes", "items": [{ "colour": "#1565c0", "label": "Cropland" }] }
    },
    {
      "id": "irrigation-practices", "section_id": "irrigation", "title": "Irrigation practices",
      "kind": "vector", "status": "no-data", "default_opacity": 0.7,
      "legend": { "type": "classes", "items": [{ "colour": "#00838f", "label": "Irrigation practice" }] }
    }
  ]
}
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -v`
Expected: all tests pass (48 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/catalogue.json backend/tests/test_real_catalogue.py
git commit -m "feat(backend): shell catalogue with all eight sections"
```

---

### Task 5: Real province and district boundaries

**This task needs the project owner.** Steps 1–4 can be done by anyone. Step 5 onward must wait until the owner has confirmed the dataset's licence and how it draws Pakistan's borders. Every other task works without it: until the files exist the portal shows "Boundaries are not loaded" and the tests use fixtures.

**Files:**
- Create: `backend/scripts/prepare_boundaries.py`
- Test: `backend/tests/test_prepare_boundaries.py`
- Create (Step 6): `backend/boundaries/provinces.geojson`, `backend/boundaries/districts.geojson`

**Interfaces:**
- Produces: `normalise(gdf, id_col, name_col, parent_col=None, tolerance=0.005) -> GeoDataFrame` with columns `id`, `name`, `parent_id`, `geometry` in EPSG:4326, matching the boundary file contract in Task 2.

- [ ] **Step 1: Add the data-preparation dependency**

```bash
uv add --dev geopandas
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_prepare_boundaries.py`:

```python
import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from prepare_boundaries import normalise  # noqa: E402


def _frame(crs="EPSG:4326"):
    return gpd.GeoDataFrame(
        {"CODE": ["PK2", "PK1"], "NAME": [" Beta ", "Alpha"], "PARENT": ["PK", "PK"]},
        geometry=[box(70, 26, 74, 30), box(66, 26, 70, 30)],
        crs=crs,
    )


def test_normalise_renames_sorts_and_trims():
    out = normalise(_frame(), "CODE", "NAME")
    assert list(out.columns) == ["id", "name", "parent_id", "geometry"]
    assert list(out["id"]) == ["PK1", "PK2"]
    assert list(out["name"]) == ["Alpha", "Beta"]
    assert list(out["parent_id"]) == ["PK", "PK"]


def test_normalise_uses_parent_column():
    frame = _frame()
    frame["PARENT"] = ["PK9", "PK8"]
    out = normalise(frame, "CODE", "NAME", "PARENT")
    assert list(out["parent_id"]) == ["PK8", "PK9"]


def test_normalise_reprojects_to_wgs84():
    out = normalise(_frame().to_crs("EPSG:3857"), "CODE", "NAME")
    assert out.crs.to_epsg() == 4326
    assert out.total_bounds == pytest.approx([66, 26, 74, 30], abs=0.01)


def test_normalise_reports_missing_columns():
    with pytest.raises(ValueError, match="ADM1_PCODE"):
        normalise(_frame(), "ADM1_PCODE", "NAME")


def test_normalise_rejects_duplicate_ids():
    frame = _frame()
    frame["CODE"] = ["PK1", "PK1"]
    with pytest.raises(ValueError, match="PK1"):
        normalise(frame, "CODE", "NAME")


def test_normalise_rejects_missing_crs():
    with pytest.raises(ValueError, match="coordinate reference system"):
        normalise(_frame(crs=None), "CODE", "NAME")
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest backend/tests/test_prepare_boundaries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prepare_boundaries'`

- [ ] **Step 4: Implement the script, run tests, commit**

`backend/scripts/prepare_boundaries.py`:

```python
"""Turn downloaded administrative boundary files into the portal's boundary GeoJSON.

Example:
    uv run python backend/scripts/prepare_boundaries.py \
        --provinces downloads/adm1.shp --province-id ADM1_PCODE --province-name ADM1_EN \
        --districts downloads/adm2.shp --district-id ADM2_PCODE --district-name ADM2_EN \
        --district-parent ADM1_PCODE
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "boundaries"


def normalise(
    gdf: gpd.GeoDataFrame,
    id_col: str,
    name_col: str,
    parent_col: str | None = None,
    tolerance: float = 0.005,
) -> gpd.GeoDataFrame:
    missing = [c for c in (id_col, name_col, parent_col) if c and c not in gdf.columns]
    if missing:
        raise ValueError(f"Missing columns {missing}; available: {list(gdf.columns)}")
    if gdf.crs is None:
        raise ValueError("The file has no coordinate reference system")
    gdf = gdf.to_crs(4326)
    out = gpd.GeoDataFrame(
        {
            "id": gdf[id_col].astype(str).str.strip(),
            "name": gdf[name_col].astype(str).str.strip(),
            "parent_id": gdf[parent_col].astype(str).str.strip() if parent_col else "PK",
        },
        geometry=gdf.geometry.simplify(tolerance, preserve_topology=True),
        crs=4326,
    )
    out = out[out.geometry.notna() & ~out.geometry.is_empty]
    duplicated = out.loc[out["id"].duplicated(), "id"].tolist()
    if duplicated:
        raise ValueError(f"Duplicate ids: {sorted(set(duplicated))}")
    return out.sort_values("name").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provinces", required=True, type=Path)
    parser.add_argument("--province-id", required=True)
    parser.add_argument("--province-name", required=True)
    parser.add_argument("--districts", required=True, type=Path)
    parser.add_argument("--district-id", required=True)
    parser.add_argument("--district-name", required=True)
    parser.add_argument("--district-parent", required=True)
    parser.add_argument("--tolerance", type=float, default=0.005)
    args = parser.parse_args()

    provinces = normalise(
        gpd.read_file(args.provinces), args.province_id, args.province_name,
        tolerance=args.tolerance,
    )
    districts = normalise(
        gpd.read_file(args.districts), args.district_id, args.district_name,
        args.district_parent, tolerance=args.tolerance,
    )
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "provinces.geojson").write_text(provinces.to_json(drop_id=True), encoding="utf-8")
    (OUTPUT_DIR / "districts.geojson").write_text(districts.to_json(drop_id=True), encoding="utf-8")
    print(f"Wrote {len(provinces)} provinces and {len(districts)} districts to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
```

Run: `uv run pytest backend/tests/test_prepare_boundaries.py -v`
Expected: 6 passed

```bash
git add pyproject.toml uv.lock backend/scripts backend/tests/test_prepare_boundaries.py
git commit -m "feat(backend): boundary preparation script"
```

- [ ] **Step 5: Owner decision — stop here until confirmed**

Download Pakistan's administrative level 1 (province) and level 2 (district) boundaries. The spec's candidate is the OCHA common operational dataset on the Humanitarian Data Exchange (data.humdata.org, search "Pakistan subnational administrative boundaries"). Save the files outside the repo.

Give the project owner, in writing: the dataset name and download page, its licence text, and a screenshot of the province layer showing how the national border and disputed areas are drawn. Do not continue until the owner replies that both the licence and the border depiction are acceptable. If they are not, ask the owner which dataset to use instead and repeat this step.

- [ ] **Step 6: Generate the boundary files**

List the columns first, because column names differ between dataset editions:

```bash
uv run python -c "import geopandas as gpd, sys; [print(p, list(gpd.read_file(p).columns)) for p in sys.argv[1:]]" path/to/adm1.shp path/to/adm2.shp
```

Run the script with the code and name columns you see (the example in the script's docstring shows the usual OCHA names):

```bash
uv run python backend/scripts/prepare_boundaries.py --provinces path/to/adm1.shp --province-id ADM1_PCODE --province-name ADM1_EN --districts path/to/adm2.shp --district-id ADM2_PCODE --district-name ADM2_EN --district-parent ADM1_PCODE
```

Expected: `Wrote N provinces and M districts to ...backend/boundaries`. Each output file should be under 5 MB; if not, re-run with `--tolerance 0.01`.

- [ ] **Step 7: Verify and commit**

Run: `uv run python -c "import sys; sys.path.insert(0, 'backend'); from csa_portal.places import load_places; i = load_places('backend/boundaries'); print(i.loaded, len(i.places))"`
Expected: `True` and the number of provinces plus districts plus one.

In `frontend/src/components/AboutDialog.tsx`, replace the line that reads "Administrative boundaries: source to be confirmed by the project owner." with one naming the confirmed dataset and its licence. That file is created in Task 9; if this step is reached first, leave the edit for Task 9 and commit only `backend/boundaries` now.

```bash
git add backend/boundaries frontend/src/components/AboutDialog.tsx
git commit -m "feat: province and district boundaries"
```

---

### Task 6: Frontend scaffold, API client and the dev command

**Files:**
- Create: `frontend/` via Vite's `react-ts` template
- Modify: `frontend/vite.config.ts`, `frontend/package.json`
- Create: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`
- Create: `package.json` (repo root)

**Interfaces:**
- Produces (types): `YearRange`, `Legend`, `Section`, `Layer`, `Catalogue`, `Place`, `PlaceLevel`, `Figure`, `SectionData`, `Boundaries`.
- Produces (client): `ApiError(status, reason, message)`, `BackendUnreachableError`, `fetchCatalogue()`, `fetchPlaces()`, `fetchBoundaries(level)` returning `null` when not loaded, `fetchSectionData(sectionId, placeId, year)`, `fetchHealth()`, `tileUrlTemplate(layerId, year, retry)`, `probeTile(layerId, year, retry)`.

- [ ] **Step 1: Scaffold and install**

```bash
npm create vite@latest frontend -- --template react-ts
npm --prefix frontend install
npm --prefix frontend install maplibre-gl zustand lucide-react
npm --prefix frontend install --save-dev vitest @playwright/test @types/geojson @types/node
npm --prefix frontend exec playwright install chromium
```

Delete the template's demo files: `frontend/src/App.css`, `frontend/src/assets/`, `frontend/public/vite.svg`. Empty `frontend/src/index.css` references are removed in Task 9 when `main.tsx` is rewritten.

In `frontend/package.json`, add to `"scripts"`:

```json
"test": "vitest run",
"e2e": "playwright test"
```

- [ ] **Step 2: Configure Vite**

Replace `frontend/vite.config.ts`:

```ts
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const backend = process.env.CSA_BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.CSA_FRONTEND_PORT ?? 5173),
    strictPort: true,
    proxy: {
      '/api': {
        target: backend,
        changeOrigin: true,
        // Answer 502 when the backend is down, so the client can tell
        // "backend unreachable" apart from a backend error.
        configure: (proxy) => {
          proxy.on('error', (_err, _req, res) => {
            if ('writeHead' in res && !res.headersSent) {
              res.writeHead(502, { 'Content-Type': 'application/json' })
            }
            res.end(JSON.stringify({ detail: { message: 'Backend unreachable', reason: 'unreachable' } }))
          })
        },
      },
    },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
```

- [ ] **Step 3: Write the types**

`frontend/src/api/types.ts`:

```ts
import type { FeatureCollection } from 'geojson'

export interface YearRange {
  first: number
  last: number
}

export interface LegendItem {
  colour: string
  label: string
}

export type Legend =
  | { type: 'classes'; items: LegendItem[] }
  | { type: 'ramp'; colours: string[]; min: number; max: number; unit: string }

export type SectionStatus = 'ready' | 'no-data' | 'coming-soon'
export type PlaceLevel = 'national' | 'province' | 'district'

export interface Section {
  id: string
  title: string
  icon: string
  order: number
  status: SectionStatus
  summary: string
  place_levels: PlaceLevel[]
  years: YearRange | null
}

export interface Layer {
  id: string
  section_id: string | null
  title: string
  kind: 'raster' | 'vector' | 'boundary'
  status: 'ready' | 'no-data'
  legend: Legend | null
  years: YearRange | null
  default_opacity: number
}

export interface Catalogue {
  basemap_style_url: string
  sections: Section[]
  layers: Layer[]
}

export interface Place {
  id: string
  name: string
  level: PlaceLevel
  parent_id: string | null
  bbox: [number, number, number, number]
}

export interface Figure {
  label: string
  value: number | string
  unit: string
}

export interface SectionData {
  section_id: string
  place_id: string
  level_used: PlaceLevel
  year: number | null
  figures: Figure[]
  charts: unknown[]
}

export interface Boundaries {
  province: FeatureCollection | null
  district: FeatureCollection | null
}

export const COUNTRY_ID = 'PK'
```

- [ ] **Step 4: Write the failing client tests**

`frontend/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  BackendUnreachableError,
  fetchBoundaries,
  fetchCatalogue,
  fetchSectionData,
  probeTile,
  tileUrlTemplate,
} from './client'

function respond(status: number, body: unknown) {
  return vi.fn(async (_url: string) => new Response(body === null ? null : JSON.stringify(body), { status }))
}

afterEach(() => vi.unstubAllGlobals())

describe('client', () => {
  it('returns parsed JSON on success', async () => {
    vi.stubGlobal('fetch', respond(200, { sections: [], layers: [], basemap_style_url: 'x' }))
    expect((await fetchCatalogue()).basemap_style_url).toBe('x')
  })

  it('throws BackendUnreachableError when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('failed') }))
    await expect(fetchCatalogue()).rejects.toBeInstanceOf(BackendUnreachableError)
  })

  it.each([502, 503, 504])('throws BackendUnreachableError on %i', async (status) => {
    vi.stubGlobal('fetch', respond(status, { detail: { message: 'x', reason: 'unreachable' } }))
    await expect(fetchCatalogue()).rejects.toBeInstanceOf(BackendUnreachableError)
  })

  it('throws ApiError carrying status, reason and message', async () => {
    vi.stubGlobal('fetch', respond(404, { detail: { message: 'Unknown section', reason: 'not-found' } }))
    const error = await fetchSectionData('ghost', null, null).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(404)
    expect(error.reason).toBe('not-found')
    expect(error.message).toBe('Unknown section')
  })

  it('copes with error bodies that are not the expected shape', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Internal Server Error', { status: 500 })))
    const error = await fetchCatalogue().catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.reason).toBeNull()
  })

  it('returns null boundaries when they are not loaded', async () => {
    vi.stubGlobal('fetch', respond(404, { detail: { message: 'none', reason: 'no-data' } }))
    expect(await fetchBoundaries('province')).toBeNull()
  })

  it('builds section data URLs, omitting absent values', async () => {
    const fetchMock = respond(200, {})
    vi.stubGlobal('fetch', fetchMock)
    await fetchSectionData('alpha-section', null, null)
    await fetchSectionData('alpha-section', 'PK1', 2005)
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
      '/api/sections/alpha-section/data',
      '/api/sections/alpha-section/data?place=PK1&year=2005',
    ])
  })

  it('builds tile URL templates', () => {
    expect(tileUrlTemplate('forest', null, 0)).toBe('/api/tiles/forest/{z}/{x}/{y}')
    expect(tileUrlTemplate('forest', 2005, 0)).toBe('/api/tiles/forest/{z}/{x}/{y}?year=2005')
    expect(tileUrlTemplate('forest', 2005, 2)).toBe('/api/tiles/forest/{z}/{x}/{y}?year=2005&r=2')
  })

  it('probes the root tile and reports success or failure', async () => {
    const ok = respond(200, null)
    vi.stubGlobal('fetch', ok)
    expect(await probeTile('forest', 2005, 0)).toBe(true)
    expect(ok.mock.calls[0][0]).toBe('/api/tiles/forest/0/0/0?year=2005')
    vi.stubGlobal('fetch', respond(404, { detail: { message: 'x', reason: 'no-data' } }))
    expect(await probeTile('forest', null, 0)).toBe(false)
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('failed') }))
    expect(await probeTile('forest', null, 0)).toBe(false)
  })
})
```

- [ ] **Step 5: Run to verify failure**

Run: `npm --prefix frontend run test`
Expected: FAIL, cannot resolve `./client`

- [ ] **Step 6: Implement the client**

`frontend/src/api/client.ts`:

```ts
import type { FeatureCollection } from 'geojson'
import type { Catalogue, Place, SectionData } from './types'

export class ApiError extends Error {
  status: number
  reason: string | null

  constructor(status: number, reason: string | null, message: string) {
    super(message)
    this.status = status
    this.reason = reason
  }
}

export class BackendUnreachableError extends Error {
  constructor() {
    super('The portal cannot reach its data service.')
  }
}

const GATEWAY_STATUSES = [502, 503, 504]

async function getJson<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(path)
  } catch {
    throw new BackendUnreachableError()
  }
  if (GATEWAY_STATUSES.includes(response.status)) throw new BackendUnreachableError()
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' ? (body as { detail?: unknown }).detail : null
    const shaped = detail && typeof detail === 'object' ? (detail as { message?: unknown; reason?: unknown }) : null
    throw new ApiError(
      response.status,
      typeof shaped?.reason === 'string' ? shaped.reason : null,
      typeof shaped?.message === 'string' ? shaped.message : `Request failed (${response.status})`,
    )
  }
  return (await response.json()) as T
}

export const fetchCatalogue = () => getJson<Catalogue>('/api/catalogue')
export const fetchPlaces = () => getJson<Place[]>('/api/places')
export const fetchHealth = () => getJson<{ status: string }>('/api/health')

export async function fetchBoundaries(level: 'province' | 'district'): Promise<FeatureCollection | null> {
  try {
    return await getJson<FeatureCollection>(`/api/places/boundaries?level=${level}`)
  } catch (error) {
    if (error instanceof ApiError && error.reason === 'no-data') return null
    throw error
  }
}

export function fetchSectionData(sectionId: string, placeId: string | null, year: number | null) {
  const params: string[] = []
  if (placeId) params.push(`place=${encodeURIComponent(placeId)}`)
  if (year !== null) params.push(`year=${year}`)
  const query = params.length ? `?${params.join('&')}` : ''
  return getJson<SectionData>(`/api/sections/${sectionId}/data${query}`)
}

export function tileUrlTemplate(layerId: string, year: number | null, retry: number): string {
  const params: string[] = []
  if (year !== null) params.push(`year=${year}`)
  if (retry > 0) params.push(`r=${retry}`)
  const query = params.length ? `?${params.join('&')}` : ''
  return `/api/tiles/${layerId}/{z}/{x}/{y}${query}`
}

/** Ask for the root tile to learn whether a layer's tiles can be served at all. */
export async function probeTile(layerId: string, year: number | null, retry: number): Promise<boolean> {
  try {
    const response = await fetch(tileUrlTemplate(layerId, year, retry).replace('{z}/{x}/{y}', '0/0/0'))
    return response.ok
  } catch {
    return false
  }
}
```

- [ ] **Step 7: Run to verify pass**

Run: `npm --prefix frontend run test`
Expected: 11 passed

- [ ] **Step 8: Add the root dev command**

Create `package.json` at the repo root:

```json
{
  "name": "csa-portal",
  "private": true,
  "scripts": {
    "dev": "concurrently -k -n api,web \"uv run uvicorn csa_portal.main:create_app --factory --app-dir backend --port 8000\" \"npm --prefix frontend run dev -- --open\"",
    "test": "uv run pytest && npm --prefix frontend run test && npm --prefix frontend run e2e"
  }
}
```

```bash
npm install --save-dev concurrently
```

- [ ] **Step 9: Verify both halves start**

Run: `npm run dev`
Expected: two labelled log streams, `api` reporting `Uvicorn running on http://127.0.0.1:8000` and `web` reporting the Vite URL, and the browser opens the Vite template page. In a second terminal: `curl http://localhost:5173/api/health` returns `{"status":"ok",...}`. Stop with Ctrl+C.

- [ ] **Step 10: Commit**

```bash
git add package.json package-lock.json frontend
git commit -m "feat(frontend): scaffold, API client and dev command"
```

---

### Task 7: View state, UI state and selectors

**Files:**
- Create: `frontend/src/state/viewState.ts`, `frontend/src/state/uiState.ts`, `frontend/src/state/selectors.ts`
- Test: `frontend/src/state/viewState.test.ts`, `frontend/src/state/uiState.test.ts`, `frontend/src/state/selectors.test.ts`

**Interfaces:**
- Produces (view): `ActiveLayer {id, opacity, hidden}`, `View {section, layers, place, year}`, `emptyView`, `createViewStore(initial?)`, `viewStore`, `useView(selector)`, `pickView(state)`. Actions: `openSection(id)`, `closeSection()`, `toggleLayer(id, defaultOpacity)`, `removeLayer(id)`, `setOpacity(id, opacity)`, `toggleHidden(id)`, `moveLayer(id, toIndex)`, `selectPlace(id | null)`, `setYear(year | null)`, `replaceView(view)`. `layers[0]` is the top layer.
- Produces (ui): `createUiStore()`, `uiStore`, `useUi(selector)`. State: `notices: {id, text}[]`, `layerErrors`, `retryCounts`, `backendLost`. Actions: `addNotice(text)`, `dismissNotice(id)`, `setLayerError(id)`, `clearLayerError(id)`, `retryLayer(id)`, `forgetLayer(id)`, `setBackendLost(lost)`.
- Produces (selectors): `timeRange(view, catalogue)`, `effectiveYear(years, year)`, `sectionsWithActiveLayers(view, catalogue)`, `ancestors(places, placeId)`, `clickTarget(places, selectedId, clickedDistrictId)`, `searchPlaces(places, query, limit?)`.
- Rule for components: select one value per `useView`/`useUi` call (`useView((s) => s.layers)`). A selector that builds a new object or array on every call re-renders forever.

- [ ] **Step 1: Write the failing view state tests**

`frontend/src/state/viewState.test.ts`:

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { createViewStore, pickView } from './viewState'

let store: ReturnType<typeof createViewStore>
const ids = () => store.getState().layers.map((l) => l.id)

beforeEach(() => {
  store = createViewStore()
})

describe('sections', () => {
  it('opens, switches and toggles closed', () => {
    store.getState().openSection('a')
    expect(store.getState().section).toBe('a')
    store.getState().openSection('b')
    expect(store.getState().section).toBe('b')
    store.getState().openSection('b')
    expect(store.getState().section).toBeNull()
  })

  it('keeps layers when the section changes or closes', () => {
    store.getState().openSection('a')
    store.getState().toggleLayer('x', 1)
    store.getState().openSection('b')
    store.getState().closeSection()
    expect(ids()).toEqual(['x'])
  })
})

describe('layers', () => {
  it('adds new layers on top with their default opacity', () => {
    store.getState().toggleLayer('x', 0.8)
    store.getState().toggleLayer('y', 1)
    expect(store.getState().layers).toEqual([
      { id: 'y', opacity: 1, hidden: false },
      { id: 'x', opacity: 0.8, hidden: false },
    ])
  })

  it('toggling an active layer removes it', () => {
    store.getState().toggleLayer('x', 1)
    store.getState().toggleLayer('x', 1)
    expect(ids()).toEqual([])
  })

  it('removes, hides and sets opacity', () => {
    store.getState().toggleLayer('x', 1)
    store.getState().toggleLayer('y', 1)
    store.getState().toggleHidden('x')
    store.getState().setOpacity('y', 0.35)
    expect(store.getState().layers).toEqual([
      { id: 'y', opacity: 0.35, hidden: false },
      { id: 'x', opacity: 1, hidden: true },
    ])
    store.getState().removeLayer('y')
    expect(ids()).toEqual(['x'])
  })

  it('clamps and rounds opacity, and ignores NaN', () => {
    store.getState().toggleLayer('x', 5)
    expect(store.getState().layers[0].opacity).toBe(1)
    store.getState().setOpacity('x', -3)
    expect(store.getState().layers[0].opacity).toBe(0)
    store.getState().setOpacity('x', 0.8500000001)
    expect(store.getState().layers[0].opacity).toBe(0.85)
    store.getState().setOpacity('x', Number.NaN)
    expect(store.getState().layers[0].opacity).toBe(0.85)
  })

  it('reorders, clamping the target index', () => {
    for (const id of ['c', 'b', 'a']) store.getState().toggleLayer(id, 1)
    expect(ids()).toEqual(['a', 'b', 'c'])
    store.getState().moveLayer('c', 0)
    expect(ids()).toEqual(['c', 'a', 'b'])
    store.getState().moveLayer('c', 99)
    expect(ids()).toEqual(['a', 'b', 'c'])
    store.getState().moveLayer('b', -4)
    expect(ids()).toEqual(['b', 'a', 'c'])
    store.getState().moveLayer('ghost', 0)
    expect(ids()).toEqual(['b', 'a', 'c'])
  })

  it('ignores actions on layers that are not active', () => {
    store.getState().setOpacity('ghost', 0.5)
    store.getState().toggleHidden('ghost')
    store.getState().removeLayer('ghost')
    expect(ids()).toEqual([])
  })
})

describe('place and year', () => {
  it('selects a province then a district, then steps back', () => {
    store.getState().selectPlace('PK1')
    store.getState().selectPlace('PK101')
    expect(store.getState().place).toBe('PK101')
    store.getState().selectPlace('PK1')
    expect(store.getState().place).toBe('PK1')
    store.getState().selectPlace(null)
    expect(store.getState().place).toBeNull()
  })

  it('treats the country id as no selection', () => {
    store.getState().selectPlace('PK')
    expect(store.getState().place).toBeNull()
  })

  it('sets and clears the year', () => {
    store.getState().setYear(2005)
    expect(store.getState().year).toBe(2005)
    store.getState().setYear(null)
    expect(store.getState().year).toBeNull()
  })
})

describe('replaceView and pickView', () => {
  it('round-trips a whole view', () => {
    const view = {
      section: 'a',
      layers: [{ id: 'x', opacity: 0.5, hidden: true }],
      place: 'PK1',
      year: 2001,
    }
    store.getState().replaceView(view)
    expect(pickView(store.getState())).toEqual(view)
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npm --prefix frontend run test -- src/state/viewState.test.ts`
Expected: FAIL, cannot resolve `./viewState`

- [ ] **Step 3: Implement the view store**

`frontend/src/state/viewState.ts`:

```ts
import { useStore } from 'zustand'
import { createStore, type StoreApi } from 'zustand/vanilla'
import { COUNTRY_ID } from '../api/types'

export interface ActiveLayer {
  id: string
  opacity: number
  hidden: boolean
}

/** Everything that describes what is on screen. `layers[0]` draws on top. */
export interface View {
  section: string | null
  layers: ActiveLayer[]
  place: string | null
  year: number | null
}

export interface ViewActions {
  openSection(id: string): void
  closeSection(): void
  toggleLayer(id: string, defaultOpacity: number): void
  removeLayer(id: string): void
  setOpacity(id: string, opacity: number): void
  toggleHidden(id: string): void
  moveLayer(id: string, toIndex: number): void
  selectPlace(id: string | null): void
  setYear(year: number | null): void
  replaceView(view: View): void
}

export type ViewStore = View & ViewActions

export const emptyView: View = { section: null, layers: [], place: null, year: null }

const tidyOpacity = (value: number) => Math.round(Math.min(1, Math.max(0, value)) * 100) / 100

export function createViewStore(initial: View = emptyView): StoreApi<ViewStore> {
  return createStore<ViewStore>()((set) => ({
    ...initial,
    openSection: (id) => set((s) => ({ section: s.section === id ? null : id })),
    closeSection: () => set({ section: null }),
    toggleLayer: (id, defaultOpacity) =>
      set((s) =>
        s.layers.some((l) => l.id === id)
          ? { layers: s.layers.filter((l) => l.id !== id) }
          : { layers: [{ id, opacity: tidyOpacity(defaultOpacity), hidden: false }, ...s.layers] },
      ),
    removeLayer: (id) => set((s) => ({ layers: s.layers.filter((l) => l.id !== id) })),
    setOpacity: (id, opacity) =>
      set((s) =>
        Number.isNaN(opacity)
          ? s
          : { layers: s.layers.map((l) => (l.id === id ? { ...l, opacity: tidyOpacity(opacity) } : l)) },
      ),
    toggleHidden: (id) =>
      set((s) => ({ layers: s.layers.map((l) => (l.id === id ? { ...l, hidden: !l.hidden } : l)) })),
    moveLayer: (id, toIndex) =>
      set((s) => {
        const from = s.layers.findIndex((l) => l.id === id)
        if (from < 0) return s
        const next = [...s.layers]
        const [moved] = next.splice(from, 1)
        next.splice(Math.min(next.length, Math.max(0, toIndex)), 0, moved)
        return { layers: next }
      }),
    selectPlace: (id) => set({ place: id === COUNTRY_ID ? null : id }),
    setYear: (year) => set({ year }),
    replaceView: (view) => set({ ...view }),
  }))
}

export const viewStore = createViewStore()

export function useView<T>(selector: (state: ViewStore) => T): T {
  return useStore(viewStore, selector)
}

export function pickView(state: View): View {
  return { section: state.section, layers: state.layers, place: state.place, year: state.year }
}
```

Run: `npm --prefix frontend run test -- src/state/viewState.test.ts`
Expected: 12 passed

- [ ] **Step 4: Write the failing UI state tests**

`frontend/src/state/uiState.test.ts`:

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { createUiStore } from './uiState'

let store: ReturnType<typeof createUiStore>

beforeEach(() => {
  store = createUiStore()
})

describe('notices', () => {
  it('adds, de-duplicates and dismisses', () => {
    store.getState().addNotice('one')
    store.getState().addNotice('one')
    store.getState().addNotice('two')
    expect(store.getState().notices.map((n) => n.text)).toEqual(['one', 'two'])
    store.getState().dismissNotice(store.getState().notices[0].id)
    expect(store.getState().notices.map((n) => n.text)).toEqual(['two'])
  })
})

describe('layer errors', () => {
  it('marks and clears an error', () => {
    store.getState().setLayerError('x')
    expect(store.getState().layerErrors).toEqual({ x: true })
    store.getState().clearLayerError('x')
    expect(store.getState().layerErrors).toEqual({})
  })

  it('retry clears the error and bumps the count', () => {
    store.getState().setLayerError('x')
    store.getState().retryLayer('x')
    store.getState().retryLayer('x')
    expect(store.getState().layerErrors).toEqual({})
    expect(store.getState().retryCounts).toEqual({ x: 2 })
  })

  it('forgetLayer drops both, and is a no-op for unknown layers', () => {
    store.getState().setLayerError('x')
    store.getState().retryLayer('x')
    const before = store.getState().retryCounts
    store.getState().forgetLayer('ghost')
    expect(store.getState().retryCounts).toBe(before)
    store.getState().forgetLayer('x')
    expect(store.getState().retryCounts).toEqual({})
    expect(store.getState().layerErrors).toEqual({})
  })
})

describe('backend lost', () => {
  it('sets and clears', () => {
    store.getState().setBackendLost(true)
    expect(store.getState().backendLost).toBe(true)
    store.getState().setBackendLost(false)
    expect(store.getState().backendLost).toBe(false)
  })
})
```

- [ ] **Step 5: Implement the UI store**

`frontend/src/state/uiState.ts`:

```ts
import { useStore } from 'zustand'
import { createStore, type StoreApi } from 'zustand/vanilla'

export interface Notice {
  id: number
  text: string
}

/** Transient interface state that does not belong in the URL. */
export interface UiStore {
  notices: Notice[]
  layerErrors: Record<string, boolean>
  retryCounts: Record<string, number>
  backendLost: boolean
  addNotice(text: string): void
  dismissNotice(id: number): void
  setLayerError(id: string): void
  clearLayerError(id: string): void
  retryLayer(id: string): void
  forgetLayer(id: string): void
  setBackendLost(lost: boolean): void
}

function without<T>(record: Record<string, T>, key: string): Record<string, T> {
  const next = { ...record }
  delete next[key]
  return next
}

export function createUiStore(): StoreApi<UiStore> {
  let nextId = 1
  return createStore<UiStore>()((set) => ({
    notices: [],
    layerErrors: {},
    retryCounts: {},
    backendLost: false,
    addNotice: (text) =>
      set((s) => (s.notices.some((n) => n.text === text) ? s : { notices: [...s.notices, { id: nextId++, text }] })),
    dismissNotice: (id) => set((s) => ({ notices: s.notices.filter((n) => n.id !== id) })),
    setLayerError: (id) => set((s) => (s.layerErrors[id] ? s : { layerErrors: { ...s.layerErrors, [id]: true } })),
    clearLayerError: (id) => set((s) => (s.layerErrors[id] ? { layerErrors: without(s.layerErrors, id) } : s)),
    retryLayer: (id) =>
      set((s) => ({
        layerErrors: without(s.layerErrors, id),
        retryCounts: { ...s.retryCounts, [id]: (s.retryCounts[id] ?? 0) + 1 },
      })),
    forgetLayer: (id) =>
      set((s) =>
        id in s.layerErrors || id in s.retryCounts
          ? { layerErrors: without(s.layerErrors, id), retryCounts: without(s.retryCounts, id) }
          : s,
      ),
    setBackendLost: (lost) => set((s) => (s.backendLost === lost ? s : { backendLost: lost })),
  }))
}

export const uiStore = createUiStore()

export function useUi<T>(selector: (state: UiStore) => T): T {
  return useStore(uiStore, selector)
}
```

Run: `npm --prefix frontend run test -- src/state/uiState.test.ts`
Expected: 5 passed

- [ ] **Step 6: Write the failing selector tests**

`frontend/src/state/selectors.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { Catalogue, Layer, Place, Section } from '../api/types'
import {
  ancestors,
  clickTarget,
  effectiveYear,
  searchPlaces,
  sectionsWithActiveLayers,
  timeRange,
} from './selectors'
import { emptyView, type View } from './viewState'

const section = (id: string, years: Section['years'] = null): Section => ({
  id, title: id, icon: 'trees', order: 1, status: 'ready', summary: '', place_levels: ['national'], years,
})
const layer = (id: string, sectionId: string, years: Layer['years'] = null): Layer => ({
  id, section_id: sectionId, title: id, kind: 'raster', status: 'ready',
  legend: { type: 'classes', items: [{ colour: '#000', label: id }] }, years, default_opacity: 1,
})
const catalogue: Catalogue = {
  basemap_style_url: '',
  sections: [section('yearly', { first: 2000, last: 2010 }), section('static')],
  layers: [
    layer('ly', 'yearly', { first: 1995, last: 2005 }),
    layer('ls', 'static'),
    layer('lz', 'static', { first: 2008, last: 2020 }),
  ],
}
const place = (id: string, name: string, level: Place['level'], parent: string | null): Place => ({
  id, name, level, parent_id: parent, bbox: [0, 0, 1, 1],
})
const places: Place[] = [
  place('PK', 'Pakistan', 'national', null),
  place('PK1', 'Alpha', 'province', 'PK'),
  place('PK2', 'Beta', 'province', 'PK'),
  place('PK101', 'District One', 'district', 'PK1'),
  place('PK102', 'District Two', 'district', 'PK1'),
  place('PK201', 'District Three', 'district', 'PK2'),
]
const view = (patch: Partial<View>): View => ({ ...emptyView, ...patch })
const active = (id: string) => ({ id, opacity: 1, hidden: false })

describe('timeRange', () => {
  it('is null when nothing on screen has years', () => {
    expect(timeRange(view({}), catalogue)).toBeNull()
    expect(timeRange(view({ section: 'static', layers: [active('ls')] }), catalogue)).toBeNull()
  })

  it('comes from the open section', () => {
    expect(timeRange(view({ section: 'yearly' }), catalogue)).toEqual({ first: 2000, last: 2010 })
  })

  it('comes from an active layer even when its section is closed', () => {
    expect(timeRange(view({ layers: [active('ly')] }), catalogue)).toEqual({ first: 1995, last: 2005 })
  })

  it('counts hidden layers', () => {
    const hidden = { id: 'ly', opacity: 1, hidden: true }
    expect(timeRange(view({ layers: [hidden] }), catalogue)).toEqual({ first: 1995, last: 2005 })
  })

  it('is the widest span across the section and all active layers', () => {
    const v = view({ section: 'yearly', layers: [active('ly'), active('lz')] })
    expect(timeRange(v, catalogue)).toEqual({ first: 1995, last: 2020 })
  })

  it('ignores ids that are not in the catalogue', () => {
    expect(timeRange(view({ section: 'ghost', layers: [active('ghost')] }), catalogue)).toBeNull()
  })
})

describe('effectiveYear', () => {
  const years = { first: 2000, last: 2010 }
  it('is null without a range', () => {
    expect(effectiveYear(null, 2005)).toBeNull()
  })
  it('defaults to the last year', () => {
    expect(effectiveYear(years, null)).toBe(2010)
  })
  it('keeps a year inside the range and clamps one outside', () => {
    expect(effectiveYear(years, 2005)).toBe(2005)
    expect(effectiveYear(years, 1990)).toBe(2000)
    expect(effectiveYear(years, 2030)).toBe(2010)
  })
})

describe('sectionsWithActiveLayers', () => {
  it('lists the sections that own an active layer', () => {
    const result = sectionsWithActiveLayers(view({ layers: [active('ls'), active('ghost')] }), catalogue)
    expect([...result]).toEqual(['static'])
  })
})

describe('ancestors', () => {
  it('is just the country when nothing is selected', () => {
    expect(ancestors(places, null).map((p) => p.id)).toEqual(['PK'])
  })
  it('runs from the country down to the selection', () => {
    expect(ancestors(places, 'PK1').map((p) => p.id)).toEqual(['PK', 'PK1'])
    expect(ancestors(places, 'PK101').map((p) => p.id)).toEqual(['PK', 'PK1', 'PK101'])
  })
  it('falls back to the country for an unknown place', () => {
    expect(ancestors(places, 'XX').map((p) => p.id)).toEqual(['PK'])
  })
  it('is empty when no places are loaded', () => {
    expect(ancestors([], 'PK1')).toEqual([])
  })
})

describe('clickTarget', () => {
  it('selects the province first', () => {
    expect(clickTarget(places, null, 'PK101')).toBe('PK1')
  })
  it('drills into the district inside the selected province', () => {
    expect(clickTarget(places, 'PK1', 'PK101')).toBe('PK101')
  })
  it('moves between districts of the same province', () => {
    expect(clickTarget(places, 'PK101', 'PK102')).toBe('PK102')
  })
  it('switches to a different province', () => {
    expect(clickTarget(places, 'PK1', 'PK201')).toBe('PK2')
    expect(clickTarget(places, 'PK101', 'PK201')).toBe('PK2')
  })
  it('is null for a district it does not know', () => {
    expect(clickTarget(places, null, 'XX')).toBeNull()
  })
  it('selects the district directly when its province is not loaded', () => {
    const orphan = [place('PK', 'Pakistan', 'national', null), place('D1', 'Lone', 'district', 'P9')]
    expect(clickTarget(orphan, null, 'D1')).toBe('D1')
  })
})

describe('searchPlaces', () => {
  it('matches part of a name regardless of case and surrounding spaces', () => {
    expect(searchPlaces(places, '  dIsTrIcT t ').map((p) => p.id)).toEqual(['PK201', 'PK102'])
  })
  it('never returns the country', () => {
    expect(searchPlaces(places, 'pak')).toEqual([])
  })
  it('returns nothing for an empty or blank query', () => {
    expect(searchPlaces(places, '')).toEqual([])
    expect(searchPlaces(places, '   ')).toEqual([])
  })
  it('puts names that start with the query first and respects the limit', () => {
    expect(searchPlaces(places, 'a').map((p) => p.id)[0]).toBe('PK1')
    expect(searchPlaces(places, 'district', 2)).toHaveLength(2)
  })
})
```

- [ ] **Step 7: Implement the selectors**

`frontend/src/state/selectors.ts`:

```ts
import { COUNTRY_ID, type Catalogue, type Place, type YearRange } from '../api/types'
import type { View } from './viewState'

/** The time slider's range: the widest span across the open section and every active layer. */
export function timeRange(view: View, catalogue: Catalogue): YearRange | null {
  const ranges: YearRange[] = []
  const section = catalogue.sections.find((s) => s.id === view.section)
  if (section?.years) ranges.push(section.years)
  for (const active of view.layers) {
    const layer = catalogue.layers.find((l) => l.id === active.id)
    if (layer?.years) ranges.push(layer.years)
  }
  if (!ranges.length) return null
  return {
    first: Math.min(...ranges.map((r) => r.first)),
    last: Math.max(...ranges.map((r) => r.last)),
  }
}

/** The year a layer or section actually shows: its nearest available year. */
export function effectiveYear(years: YearRange | null | undefined, year: number | null): number | null {
  if (!years) return null
  if (year === null) return years.last
  return Math.min(years.last, Math.max(years.first, year))
}

export function sectionsWithActiveLayers(view: View, catalogue: Catalogue): Set<string> {
  const result = new Set<string>()
  for (const active of view.layers) {
    const sectionId = catalogue.layers.find((l) => l.id === active.id)?.section_id
    if (sectionId) result.add(sectionId)
  }
  return result
}

/** The breadcrumb trail: country first, selection last. */
export function ancestors(places: Place[], placeId: string | null): Place[] {
  const byId = new Map(places.map((p) => [p.id, p]))
  const trail: Place[] = []
  let current = byId.get(placeId ?? COUNTRY_ID) ?? byId.get(COUNTRY_ID)
  while (current && !trail.includes(current)) {
    trail.unshift(current)
    current = current.parent_id ? byId.get(current.parent_id) : undefined
  }
  return trail
}

/**
 * What a click on a district selects: the province first, then the district
 * once its province is the selection, or the new province if it is elsewhere.
 */
export function clickTarget(places: Place[], selectedId: string | null, clickedDistrictId: string): string | null {
  const byId = new Map(places.map((p) => [p.id, p]))
  const district = byId.get(clickedDistrictId)
  if (!district) return null
  const province = district.parent_id ? byId.get(district.parent_id) : undefined
  if (!province) return district.id
  const selected = selectedId ? byId.get(selectedId) : undefined
  const selectedProvinceId = selected?.level === 'district' ? selected.parent_id : selected?.id
  return selectedProvinceId === province.id ? district.id : province.id
}

export function searchPlaces(places: Place[], query: string, limit = 8): Place[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return []
  const matches = places.filter((p) => p.level !== 'national' && p.name.toLowerCase().includes(needle))
  const startsWith = (p: Place) => (p.name.toLowerCase().startsWith(needle) ? 0 : 1)
  return matches.sort((a, b) => startsWith(a) - startsWith(b) || a.name.localeCompare(b.name)).slice(0, limit)
}
```

- [ ] **Step 8: Run to verify pass**

Run: `npm --prefix frontend run test`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add frontend/src/state
git commit -m "feat(frontend): view state, UI state and selectors"
```

---

### Task 8: Address-bar state

**Files:**
- Create: `frontend/src/state/urlState.ts`, `frontend/src/state/useUrlSync.ts`
- Test: `frontend/src/state/urlState.test.ts`

**Interfaces:**
- Consumes: `View`, `emptyView`, `viewStore`, `pickView`, `uiStore`, `timeRange`, `Catalogue`, `Place`.
- Produces: `serializeView(view): string` (empty string or `?…`), `parseView(search, catalogue, places): { view: View; dropped: string[] }`, `useUrlSync(catalogue, places): void`.
- Rules: a layer may be active only if it is in the catalogue, is not a boundary and has status `ready`. An invalid opacity falls back to the layer's default and is reported. A year is kept only if it is a whole number inside `timeRange` of the parsed view.

- [ ] **Step 1: Write the failing tests**

`frontend/src/state/urlState.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { Catalogue, Layer, Place } from '../api/types'
import { parseView, serializeView } from './urlState'
import { emptyView, type View } from './viewState'

const layer = (id: string, patch: Partial<Layer> = {}): Layer => ({
  id, section_id: 'yearly', title: id, kind: 'raster', status: 'ready',
  legend: { type: 'classes', items: [{ colour: '#000', label: id }] },
  years: null, default_opacity: 0.8, ...patch,
})
const catalogue: Catalogue = {
  basemap_style_url: '',
  sections: [
    { id: 'yearly', title: 'Yearly', icon: 'trees', order: 1, status: 'ready', summary: '',
      place_levels: ['national'], years: { first: 2000, last: 2010 } },
    { id: 'static', title: 'Static', icon: 'trees', order: 2, status: 'ready', summary: '',
      place_levels: ['national'], years: null },
  ],
  layers: [
    layer('forest'),
    layer('irrigated', { section_id: 'static' }),
    layer('empty', { status: 'no-data' }),
    layer('provinces', { kind: 'boundary', section_id: null, legend: null }),
  ],
}
const places: Place[] = [
  { id: 'PK', name: 'Pakistan', level: 'national', parent_id: null, bbox: [0, 0, 1, 1] },
  { id: 'PK1', name: 'Alpha', level: 'province', parent_id: 'PK', bbox: [0, 0, 1, 1] },
]
const parse = (search: string) => parseView(search, catalogue, places)

describe('serializeView', () => {
  it('is empty for the empty view', () => {
    expect(serializeView(emptyView)).toBe('')
  })

  it('writes every part in a fixed order', () => {
    const view: View = {
      section: 'yearly',
      layers: [
        { id: 'forest', opacity: 0.8, hidden: true },
        { id: 'irrigated', opacity: 1, hidden: false },
      ],
      place: 'PK1',
      year: 2005,
    }
    expect(serializeView(view)).toBe(
      '?section=yearly&layers=forest:0.8,irrigated:1&hidden=forest&place=PK1&year=2005',
    )
  })
})

describe('parseView', () => {
  it('round-trips a full view', () => {
    const view: View = {
      section: 'yearly',
      layers: [
        { id: 'forest', opacity: 0.35, hidden: true },
        { id: 'irrigated', opacity: 1, hidden: false },
      ],
      place: 'PK1',
      year: 2005,
    }
    expect(parse(serializeView(view))).toEqual({ view, dropped: [] })
  })

  it('returns the empty view for an empty query', () => {
    expect(parse('')).toEqual({ view: emptyView, dropped: [] })
  })

  it('drops an unknown section, layer and place, and names them', () => {
    const { view, dropped } = parse('?section=nope&layers=ghost:1,forest:0.5&place=XX')
    expect(view.section).toBeNull()
    expect(view.layers).toEqual([{ id: 'forest', opacity: 0.5, hidden: false }])
    expect(view.place).toBeNull()
    expect(dropped).toEqual(['section "nope"', 'layer "ghost"', 'place "XX"'])
  })

  it('refuses layers that cannot be shown', () => {
    const { view, dropped } = parse('?layers=empty:1,provinces:1')
    expect(view.layers).toEqual([])
    expect(dropped).toEqual(['layer "empty"', 'layer "provinces"'])
  })

  it('handles garbage values without throwing', () => {
    const { view, dropped } = parse('?layers=forest:abc,forest:1,irrigated:5,,&hidden=ghost,forest&year=2015.5')
    expect(view.layers).toEqual([
      { id: 'forest', opacity: 0.8, hidden: true },
      { id: 'irrigated', opacity: 0.8, hidden: false },
    ])
    expect(view.year).toBeNull()
    expect(dropped).toEqual([
      'opacity "abc" for layer "forest"',
      'layer "forest" (repeated)',
      'opacity "5" for layer "irrigated"',
      'hidden layer "ghost"',
      'year "2015.5"',
    ])
  })

  it('uses the default opacity when none is given, without complaint', () => {
    expect(parse('?layers=forest')).toEqual({
      view: { ...emptyView, layers: [{ id: 'forest', opacity: 0.8, hidden: false }] },
      dropped: [],
    })
  })

  it('treats an empty layers parameter as no layers', () => {
    expect(parse('?layers=')).toEqual({ view: emptyView, dropped: [] })
  })

  it('reads the country id as no selection', () => {
    expect(parse('?place=PK')).toEqual({ view: emptyView, dropped: [] })
  })

  it('keeps a year only inside the range of what is on screen', () => {
    expect(parse('?section=yearly&year=2005').view.year).toBe(2005)
    expect(parse('?section=yearly&year=1800')).toEqual({
      view: { ...emptyView, section: 'yearly' },
      dropped: ['year "1800"'],
    })
    expect(parse('?section=static&year=2005').dropped).toEqual(['year "2005"'])
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npm --prefix frontend run test -- src/state/urlState.test.ts`
Expected: FAIL, cannot resolve `./urlState`

- [ ] **Step 3: Implement parsing and serializing**

`frontend/src/state/urlState.ts`:

```ts
import { COUNTRY_ID, type Catalogue, type Place } from '../api/types'
import { timeRange } from './selectors'
import type { ActiveLayer, View } from './viewState'

/** Ids are URL-safe by catalogue rule, so the query is built by hand to stay readable. */
export function serializeView(view: View): string {
  const parts: string[] = []
  if (view.section) parts.push(`section=${view.section}`)
  if (view.layers.length) parts.push(`layers=${view.layers.map((l) => `${l.id}:${l.opacity}`).join(',')}`)
  const hidden = view.layers.filter((l) => l.hidden).map((l) => l.id)
  if (hidden.length) parts.push(`hidden=${hidden.join(',')}`)
  if (view.place) parts.push(`place=${encodeURIComponent(view.place)}`)
  if (view.year !== null) parts.push(`year=${view.year}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export function parseView(search: string, catalogue: Catalogue, places: Place[]): { view: View; dropped: string[] } {
  const params = new URLSearchParams(search)
  const dropped: string[] = []

  let section: string | null = null
  const rawSection = params.get('section')
  if (rawSection) {
    if (catalogue.sections.some((s) => s.id === rawSection)) section = rawSection
    else dropped.push(`section "${rawSection}"`)
  }

  const layers: ActiveLayer[] = []
  for (const token of (params.get('layers') ?? '').split(',')) {
    if (!token) continue
    const [id, rawOpacity] = token.split(':')
    const layer = catalogue.layers.find((l) => l.id === id)
    if (!layer || layer.kind === 'boundary' || layer.status !== 'ready') {
      dropped.push(`layer "${id}"`)
      continue
    }
    if (layers.some((l) => l.id === id)) {
      dropped.push(`layer "${id}" (repeated)`)
      continue
    }
    let opacity = layer.default_opacity
    if (rawOpacity !== undefined && rawOpacity !== '') {
      const parsed = Number(rawOpacity)
      if (Number.isFinite(parsed) && parsed >= 0 && parsed <= 1) opacity = parsed
      else dropped.push(`opacity "${rawOpacity}" for layer "${id}"`)
    }
    layers.push({ id, opacity, hidden: false })
  }

  for (const id of (params.get('hidden') ?? '').split(',')) {
    if (!id) continue
    const active = layers.find((l) => l.id === id)
    if (active) active.hidden = true
    else dropped.push(`hidden layer "${id}"`)
  }

  let place: string | null = null
  const rawPlace = params.get('place')
  if (rawPlace && rawPlace !== COUNTRY_ID) {
    if (places.some((p) => p.id === rawPlace)) place = rawPlace
    else dropped.push(`place "${rawPlace}"`)
  }

  const view: View = { section, layers, place, year: null }
  const rawYear = params.get('year')
  if (rawYear) {
    const year = Number(rawYear)
    const range = timeRange(view, catalogue)
    if (Number.isInteger(year) && range && year >= range.first && year <= range.last) view.year = year
    else dropped.push(`year "${rawYear}"`)
  }

  return { view, dropped }
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npm --prefix frontend run test -- src/state/urlState.test.ts`
Expected: 11 passed

- [ ] **Step 5: Add the sync hook**

`frontend/src/state/useUrlSync.ts`:

```ts
import { useEffect } from 'react'
import type { Catalogue, Place } from '../api/types'
import { uiStore } from './uiState'
import { parseView, serializeView } from './urlState'
import { pickView, viewStore } from './viewState'

/** Read the view from the address bar once the data has loaded, then keep the address bar in step. */
export function useUrlSync(catalogue: Catalogue, places: Place[]): void {
  useEffect(() => {
    const { view, dropped } = parseView(window.location.search, catalogue, places)
    viewStore.getState().replaceView(view)
    if (dropped.length) {
      uiStore.getState().addNotice(`Ignored from the link: ${dropped.join(', ')}.`)
    }
    const write = () => {
      const query = serializeView(pickView(viewStore.getState()))
      window.history.replaceState(null, '', `${window.location.pathname}${query}`)
    }
    write()
    return viewStore.subscribe(write)
  }, [catalogue, places])
}
```

The hook is mounted in Task 9 and exercised by the end-to-end tests from then on.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/state
git commit -m "feat(frontend): address-bar state"
```

---

### Task 9: App frame, rail and section panel

**Files:**
- Create: `frontend/src/data/usePortalData.ts`, `frontend/src/data/useSectionData.ts`
- Create: `frontend/src/components/BackendDown.tsx`, `Notices.tsx`, `IconRail.tsx`, `SectionPanel.tsx`, `AboutDialog.tsx`
- Replace: `frontend/src/App.tsx`, `frontend/src/main.tsx`
- Create: `frontend/src/styles.css`; delete `frontend/src/index.css`
- Replace: `frontend/index.html` title
- Create: `frontend/playwright.config.ts`, `frontend/e2e/helpers.ts`
- Test: `frontend/e2e/frame.spec.ts`

**Interfaces:**
- Consumes: the client, both stores, `effectiveYear`, `sectionsWithActiveLayers`, `useUrlSync`.
- Produces: `PortalData { catalogue, places, boundaries }`, `usePortalData(): { state, retry }` where `state.status` is `loading | unreachable | error | ready`; `useSectionData(section, placeId, year)` returning a state whose `status` is `idle | loading | ready | no-data | coming-soon | error`.
- Produces (layout): `App.tsx` renders `<div class="app">` containing the rail, the panel and `<main class="map-area">`. Later tasks add children to `map-area`; each says exactly where.
- Produces (e2e): `openPortal(page, path?)` and `mockTiles(page)` in `e2e/helpers.ts`. The end-to-end backend runs on port 8010 with the fixture catalogue and boundaries; the frontend on 5183.

- [ ] **Step 1: Configure Playwright**

`frontend/playwright.config.ts`:

```ts
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from '@playwright/test'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const fixtures = path.join(root, 'backend', 'tests', 'fixtures')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  use: { baseURL: 'http://127.0.0.1:5183', viewport: { width: 1440, height: 900 } },
  webServer: [
    {
      command: 'uv run uvicorn csa_portal.main:create_app --factory --app-dir backend --port 8010',
      cwd: root,
      url: 'http://127.0.0.1:8010/api/health',
      reuseExistingServer: false,
      env: {
        CSA_CATALOGUE_PATH: path.join(fixtures, 'test_catalogue.json'),
        CSA_BOUNDARIES_DIR: path.join(fixtures, 'boundaries'),
        CSA_BASEMAP_STYLE_URL: 'https://basemap.test/style.json',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1',
      url: 'http://127.0.0.1:5183',
      reuseExistingServer: false,
      env: { CSA_BACKEND_URL: 'http://127.0.0.1:8010', CSA_FRONTEND_PORT: '5183' },
    },
  ],
})
```

`frontend/e2e/helpers.ts`:

```ts
import type { Page } from '@playwright/test'

const BLANK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#eef1f4' } }],
}
const TRANSPARENT_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
)

/** Serve a blank background map so tests never need the internet. */
export async function mockBasemap(page: Page) {
  await page.route('https://basemap.test/**', (route) => route.fulfill({ json: BLANK_STYLE }))
}

/** The fixture backend has no tile providers; answer tile requests with an empty image. */
export async function mockTiles(page: Page) {
  await page.route('**/api/tiles/**', (route) =>
    route.fulfill({ status: 200, contentType: 'image/png', body: TRANSPARENT_PNG }),
  )
}

export async function openPortal(page: Page, path = '/') {
  await mockBasemap(page)
  await mockTiles(page)
  await page.goto(path)
  await page.getByRole('navigation', { name: 'Sections' }).waitFor()
}
```

- [ ] **Step 2: Write the failing end-to-end tests**

`frontend/e2e/frame.spec.ts`:

```ts
import { expect, test } from '@playwright/test'
import { mockBasemap, openPortal } from './helpers'

test('opens a section and closes it so the map takes the full width', async ({ page }) => {
  await openPortal(page)
  const map = page.locator('.map-area')
  const closedWidth = (await map.boundingBox())!.width

  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeVisible()
  expect((await map.boundingBox())!.width).toBeLessThan(closedWidth)

  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeHidden()
  expect((await map.boundingBox())!.width).toBe(closedWidth)
})

test('lists every section in catalogue order and marks coming-soon ones', async ({ page }) => {
  await openPortal(page)
  const buttons = page.getByRole('navigation', { name: 'Sections' }).locator('button[data-section]')
  await expect(buttons).toHaveCount(4)
  await expect(buttons.nth(0)).toHaveAttribute('aria-label', 'Alpha section')
  await expect(buttons.nth(2)).toHaveAttribute('aria-label', 'Later section (coming soon)')
})

test('shows the coming-soon state', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Later section (coming soon)' }).click()
  await expect(page.getByText('Coming soon')).toBeVisible()
  await expect(page.getByText('Will show things later.')).toBeVisible()
})

test('shows the no-data state in every block', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Empty section' }).click()
  await expect(page.getByRole('switch', { name: 'Fake empty' })).toBeDisabled()
  await expect(page.getByText('Data not loaded yet')).toHaveCount(3)
})

test('layer switches turn layers on and mark the section in the rail', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await page.getByRole('switch', { name: 'Fake yearly' }).check()
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(page.locator('button[data-section="alpha-section"] .rail-dot')).toBeVisible()
  await expect(page.locator('button[data-section="beta-section"] .rail-dot')).toHaveCount(0)
})

test('says "National figures only" when the section has no figures at the selected level', async ({ page }) => {
  await page.route('**/api/sections/beta-section/data**', (route) =>
    route.fulfill({
      json: {
        section_id: 'beta-section', place_id: 'PK', level_used: 'national', year: null,
        figures: [{ label: 'Total', value: 12, unit: 'Mt' }], charts: [],
      },
    }),
  )
  await openPortal(page, '/?section=beta-section&place=PK1')
  await expect(page.getByText('National figures only')).toBeVisible()
  await expect(page.getByText('12 Mt')).toBeVisible()
})

test('opens the About dialog', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'About' }).click()
  await expect(page.getByRole('dialog')).toContainText('Data sources')
})

test('shows a full-screen message when the backend is off, and recovers on retry', async ({ page }) => {
  await mockBasemap(page)
  // A regex on the port, because the glob **/api/** would also block the app's own src/api modules.
  const backendCalls = /:5183\/api\//
  await page.route(backendCalls, (route) => route.abort())
  await page.goto('/')
  await expect(page.getByRole('heading', { name: "The portal can't reach its data service" })).toBeVisible()
  await expect(page.getByText('npm run dev')).toBeVisible()

  await page.unroute(backendCalls)
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('navigation', { name: 'Sections' })).toBeVisible()
})

test('shows a notice when boundaries are not loaded', async ({ page }) => {
  await page.route('**/api/places/boundaries**', (route) =>
    route.fulfill({ status: 404, json: { detail: { message: 'none', reason: 'no-data' } } }),
  )
  await openPortal(page)
  await expect(page.getByText('Boundaries are not loaded')).toBeVisible()
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeVisible()
})

test('the panel covers the map on a narrow screen and has a close button', async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 900 })
  await openPortal(page)
  await page.getByRole('button', { name: 'Alpha section' }).click()
  const panel = (await page.locator('.panel').boundingBox())!
  expect(panel.x).toBeGreaterThanOrEqual(56)
  expect(panel.x + panel.width).toBe(800)
  await page.getByRole('button', { name: 'Close panel' }).click()
  await expect(page.locator('.panel')).toHaveCount(0)
})
```

- [ ] **Step 3: Run to verify failure**

Run: `npm --prefix frontend run e2e -- frame.spec.ts`
Expected: FAIL, the Sections navigation never appears (the page is still the Vite template)

- [ ] **Step 4: Data hooks**

`frontend/src/data/usePortalData.ts`:

```ts
import { useCallback, useEffect, useState } from 'react'
import { BackendUnreachableError, fetchBoundaries, fetchCatalogue, fetchPlaces } from '../api/client'
import type { Boundaries, Catalogue, Place } from '../api/types'
import { uiStore } from '../state/uiState'

export interface PortalData {
  catalogue: Catalogue
  places: Place[]
  boundaries: Boundaries
}

export type PortalState =
  | { status: 'loading' }
  | { status: 'unreachable' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: PortalData }

/** Everything the portal needs before it can draw: catalogue, places, boundaries. */
export function usePortalData(): { state: PortalState; retry: () => void } {
  const [state, setState] = useState<PortalState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    Promise.all([fetchCatalogue(), fetchPlaces(), fetchBoundaries('province'), fetchBoundaries('district')])
      .then(([catalogue, places, province, district]) => {
        if (cancelled) return
        if (!province || !district) {
          uiStore.getState().addNotice('Boundaries are not loaded, so places cannot be selected on the map.')
        }
        const sorted = { ...catalogue, sections: [...catalogue.sections].sort((a, b) => a.order - b.order) }
        setState({ status: 'ready', data: { catalogue: sorted, places, boundaries: { province, district } } })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof BackendUnreachableError) setState({ status: 'unreachable' })
        else setState({ status: 'error', message: error instanceof Error ? error.message : String(error) })
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  const retry = useCallback(() => setAttempt((n) => n + 1), [])
  return { state, retry }
}
```

`frontend/src/data/useSectionData.ts`:

```ts
import { useEffect, useState } from 'react'
import { ApiError, BackendUnreachableError, fetchSectionData } from '../api/client'
import type { Section, SectionData } from '../api/types'
import { uiStore } from '../state/uiState'

export type SectionDataState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: SectionData }
  | { status: 'no-data' }
  | { status: 'coming-soon' }
  | { status: 'error'; message: string }

/** The open section's figures and charts for the selected place and year. */
export function useSectionData(section: Section | null, placeId: string | null, year: number | null): SectionDataState {
  const [state, setState] = useState<SectionDataState>({ status: 'idle' })
  const sectionId = section?.id ?? null
  const sectionStatus = section?.status ?? null

  useEffect(() => {
    if (!sectionId || !sectionStatus) return setState({ status: 'idle' })
    if (sectionStatus !== 'ready') return setState({ status: sectionStatus })
    let cancelled = false
    setState({ status: 'loading' })
    fetchSectionData(sectionId, placeId, year)
      .then((data) => {
        if (cancelled) return
        uiStore.getState().setBackendLost(false)
        setState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof BackendUnreachableError) {
          uiStore.getState().setBackendLost(true)
          setState({ status: 'error', message: error.message })
        } else if (error instanceof ApiError && (error.reason === 'no-data' || error.reason === 'coming-soon')) {
          setState({ status: error.reason })
        } else {
          setState({ status: 'error', message: error instanceof Error ? error.message : String(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [sectionId, sectionStatus, placeId, year])

  return state
}
```

- [ ] **Step 5: Small components**

`frontend/src/components/BackendDown.tsx`:

```tsx
export function BackendDown({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="backend-down" role="alert">
      <h1>The portal can't reach its data service</h1>
      <p>Start it from the project folder, then try again:</p>
      <pre>npm run dev</pre>
      <button type="button" onClick={onRetry}>
        Try again
      </button>
    </div>
  )
}
```

`frontend/src/components/Notices.tsx`:

```tsx
import { X } from 'lucide-react'
import { fetchHealth } from '../api/client'
import { uiStore, useUi } from '../state/uiState'

export function Notices() {
  const notices = useUi((s) => s.notices)
  const backendLost = useUi((s) => s.backendLost)

  const recheck = () => {
    fetchHealth()
      .then(() => uiStore.getState().setBackendLost(false))
      .catch(() => undefined)
  }

  if (!notices.length && !backendLost) return null
  return (
    <div className="notices" role="status">
      {backendLost && (
        <div className="notice notice-warning">
          <span>The portal has lost its data service. What is on screen is unchanged.</span>
          <button type="button" onClick={recheck}>
            Check again
          </button>
        </div>
      )}
      {notices.map((notice) => (
        <div className="notice" key={notice.id}>
          <span>{notice.text}</span>
          <button
            type="button"
            aria-label="Dismiss notice"
            onClick={() => uiStore.getState().dismissNotice(notice.id)}
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}
```

`frontend/src/components/AboutDialog.tsx`:

```tsx
import { useEffect, useRef } from 'react'

export function AboutDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog ref={ref} className="about" onClose={onClose}>
      <h2>Climate Smart Agriculture Portal</h2>
      <h3>Data sources</h3>
      <ul>
        <li>Land cover and irrigation: project datasets, loaded in a later release.</li>
        <li>Greenhouse-gas emissions: Our World in Data and national inventory figures, 1994–2021.</li>
        <li>Crop water balance and food security projections: project spreadsheets.</li>
        <li>Administrative boundaries: source to be confirmed by the project owner.</li>
        <li>Background map: OpenFreeMap, © OpenStreetMap contributors.</li>
      </ul>
      <button type="button" onClick={onClose}>
        Close
      </button>
    </dialog>
  )
}
```

- [ ] **Step 6: Icon rail**

`frontend/src/components/IconRail.tsx`:

```tsx
import {
  CalendarDays, CloudLightning, Droplets, Factory, Info, Square, Trees, Users, Waves, Wheat,
  type LucideIcon,
} from 'lucide-react'
import { useMemo } from 'react'
import type { Catalogue } from '../api/types'
import { sectionsWithActiveLayers } from '../state/selectors'
import { emptyView, useView, viewStore } from '../state/viewState'

const ICONS: Record<string, LucideIcon> = {
  trees: Trees,
  droplets: Droplets,
  factory: Factory,
  waves: Waves,
  wheat: Wheat,
  'calendar-days': CalendarDays,
  'cloud-lightning': CloudLightning,
  users: Users,
}

export function IconRail({ catalogue, onAbout }: { catalogue: Catalogue; onAbout: () => void }) {
  const open = useView((s) => s.section)
  const layers = useView((s) => s.layers)
  const marked = useMemo(() => sectionsWithActiveLayers({ ...emptyView, layers }, catalogue), [layers, catalogue])

  return (
    <nav className="rail" aria-label="Sections">
      <div className="rail-sections">
        {catalogue.sections.map((section) => {
          const Icon = ICONS[section.icon] ?? Square
          const soon = section.status === 'coming-soon'
          const label = soon ? `${section.title} (coming soon)` : section.title
          return (
            <button
              key={section.id}
              type="button"
              className={`rail-button${soon ? ' rail-soon' : ''}`}
              data-section={section.id}
              aria-label={label}
              aria-pressed={open === section.id}
              title={label}
              onClick={() => viewStore.getState().openSection(section.id)}
            >
              <Icon size={22} aria-hidden />
              {marked.has(section.id) && <span className="rail-dot" />}
              {soon && <span className="rail-soon-mark" aria-hidden>soon</span>}
            </button>
          )
        })}
      </div>
      <button type="button" className="rail-button" aria-label="About" title="About" onClick={onAbout}>
        <Info size={22} aria-hidden />
      </button>
    </nav>
  )
}
```

- [ ] **Step 7: Section panel**

`frontend/src/components/SectionPanel.tsx`:

```tsx
import { X } from 'lucide-react'
import { useState, type PointerEvent as ReactPointerEvent } from 'react'
import { COUNTRY_ID } from '../api/types'
import type { PortalData } from '../data/usePortalData'
import { useSectionData, type SectionDataState } from '../data/useSectionData'
import { effectiveYear } from '../state/selectors'
import { useView, viewStore } from '../state/viewState'

const MIN_WIDTH = 280
const MAX_WIDTH = 640

function Figures({ state, placeSelected }: { state: SectionDataState; placeSelected: boolean }) {
  if (state.status === 'no-data') return <p className="empty">Data not loaded yet</p>
  if (state.status === 'loading' || state.status === 'idle') return <p className="empty">Loading…</p>
  if (state.status === 'error') return <p className="empty">Figures could not be loaded: {state.message}</p>
  if (state.status === 'coming-soon') return null
  const { data } = state
  return (
    <>
      {placeSelected && data.level_used === 'national' && <p className="national-only">National figures only</p>}
      {data.figures.length === 0 ? (
        <p className="empty">No figures for this section yet.</p>
      ) : (
        <dl className="figures">
          {data.figures.map((figure) => (
            <div key={figure.label}>
              <dt>{figure.label}</dt>
              <dd>{[figure.value, figure.unit].filter((part) => part !== '').join(' ')}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  )
}

export function SectionPanel({ data }: { data: PortalData }) {
  const sectionId = useView((s) => s.section)
  const activeLayers = useView((s) => s.layers)
  const placeId = useView((s) => s.place)
  const year = useView((s) => s.year)
  const [width, setWidth] = useState(340)

  const section = data.catalogue.sections.find((s) => s.id === sectionId) ?? null
  const sectionData = useSectionData(section, placeId, effectiveYear(section?.years, year))
  if (!section) return null

  const place = data.places.find((p) => p.id === (placeId ?? COUNTRY_ID))
  const layers = data.catalogue.layers.filter((l) => l.section_id === section.id && l.kind !== 'boundary')

  const startResize = (event: ReactPointerEvent) => {
    const startX = event.clientX
    const startWidth = width
    const move = (e: PointerEvent) =>
      setWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + e.clientX - startX)))
    const stop = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
  }

  return (
    <aside className="panel" style={{ width }} aria-label={section.title}>
      <header className="panel-header">
        <h2>{section.title}</h2>
        <button type="button" aria-label="Close panel" onClick={() => viewStore.getState().closeSection()}>
          <X size={18} />
        </button>
      </header>

      {section.status === 'coming-soon' ? (
        <div className="panel-body">
          <p className="coming-soon">Coming soon</p>
          <p>{section.summary}</p>
        </div>
      ) : (
        <div className="panel-body">
          <section>
            <h3>Layers</h3>
            {layers.length === 0 && <p className="empty">This section has no map layers.</p>}
            {layers.map((layer) => {
              const ready = layer.status === 'ready'
              return (
                <label key={layer.id} className={`layer-switch${ready ? '' : ' disabled'}`}>
                  <input
                    type="checkbox"
                    role="switch"
                    aria-label={layer.title}
                    disabled={!ready}
                    checked={activeLayers.some((l) => l.id === layer.id)}
                    onChange={() => viewStore.getState().toggleLayer(layer.id, layer.default_opacity)}
                  />
                  <span>{layer.title}</span>
                  {!ready && <small>Data not loaded yet</small>}
                </label>
              )
            })}
          </section>
          <section>
            <h3>Figures for {place?.name ?? 'Pakistan'}</h3>
            <Figures state={sectionData} placeSelected={placeId !== null} />
          </section>
          <section>
            <h3>Charts</h3>
            <p className="empty">
              {sectionData.status === 'ready' ? 'No charts for this section yet.' : 'Data not loaded yet'}
            </p>
          </section>
        </div>
      )}
      <div className="panel-resize" onPointerDown={startResize} role="separator" aria-orientation="vertical" />
    </aside>
  )
}
```

- [ ] **Step 8: App, entry point and styles**

`frontend/src/App.tsx`:

```tsx
import { useState } from 'react'
import { AboutDialog } from './components/AboutDialog'
import { BackendDown } from './components/BackendDown'
import { IconRail } from './components/IconRail'
import { Notices } from './components/Notices'
import { SectionPanel } from './components/SectionPanel'
import { usePortalData, type PortalData } from './data/usePortalData'
import { useUrlSync } from './state/useUrlSync'

function Portal({ data }: { data: PortalData }) {
  useUrlSync(data.catalogue, data.places)
  const [aboutOpen, setAboutOpen] = useState(false)
  return (
    <div className="app">
      <IconRail catalogue={data.catalogue} onAbout={() => setAboutOpen(true)} />
      <SectionPanel data={data} />
      <main className="map-area">
        <Notices />
      </main>
      <AboutDialog open={aboutOpen} onClose={() => setAboutOpen(false)} />
    </div>
  )
}

export default function App() {
  const { state, retry } = usePortalData()
  if (state.status === 'loading') return <div className="splash">Loading the portal…</div>
  if (state.status === 'unreachable') return <BackendDown onRetry={retry} />
  if (state.status === 'error') {
    return (
      <div className="backend-down" role="alert">
        <h1>The portal could not load its data</h1>
        <p>{state.message}</p>
        <button type="button" onClick={retry}>
          Try again
        </button>
      </div>
    )
  }
  return <Portal data={state.data} />
}
```

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

Delete `frontend/src/index.css`. In `frontend/index.html` set `<title>CSA Portal</title>` and remove the `vite.svg` icon link.

`frontend/src/styles.css`:

```css
:root {
  --rail-width: 56px;
  --ink: #0f172a;
  --muted: #64748b;
  --line: #e2e8f0;
  --surface: #ffffff;
  --accent: #1d4ed8;
  --warning: #b45309;
  font-family: system-ui, 'Segoe UI', sans-serif;
  color: var(--ink);
}

* { box-sizing: border-box; }
html, body, #root { height: 100%; margin: 0; }
button { font: inherit; cursor: pointer; }
h2, h3 { margin: 0; }

.app { display: flex; height: 100%; position: relative; }

.splash, .backend-down {
  height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px; padding: 24px; text-align: center;
}
.backend-down pre { background: #f1f5f9; padding: 8px 16px; border-radius: 6px; }

/* Rail */
.rail {
  width: var(--rail-width); flex: none; display: flex; flex-direction: column;
  justify-content: space-between; background: var(--ink); padding: 8px 0; z-index: 30;
}
.rail-sections { display: flex; flex-direction: column; gap: 4px; }
.rail-button {
  position: relative; width: 44px; height: 44px; margin: 0 auto; border: 0; border-radius: 8px;
  background: transparent; color: #cbd5e1; display: grid; place-items: center;
}
.rail-button:hover { background: #1e293b; color: #fff; }
.rail-button[aria-pressed='true'] { background: var(--accent); color: #fff; }
.rail-dot {
  position: absolute; top: 6px; right: 6px; width: 8px; height: 8px;
  border-radius: 50%; background: #22c55e;
}
.rail-soon { opacity: 0.6; }
.rail-soon-mark { position: absolute; bottom: 1px; font-size: 8px; text-transform: uppercase; }

/* Panel */
.panel {
  flex: none; position: relative; display: flex; flex-direction: column;
  background: var(--surface); border-right: 1px solid var(--line); z-index: 20;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--line);
}
.panel-header h2 { font-size: 18px; }
.panel-header button { border: 0; background: transparent; }
.panel-body { overflow-y: auto; padding: 8px 16px 24px; }
.panel-body section { padding: 12px 0; border-bottom: 1px solid var(--line); }
.panel-body h3 { font-size: 13px; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }
.panel-resize { position: absolute; top: 0; right: -3px; width: 6px; height: 100%; cursor: col-resize; }
.layer-switch { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 4px 0; }
.layer-switch.disabled { color: var(--muted); }
.layer-switch small { flex-basis: 100%; padding-left: 24px; }
.empty { color: var(--muted); margin: 0; }
.coming-soon { font-size: 20px; font-weight: 600; }
.national-only { color: var(--warning); font-weight: 600; margin: 0 0 8px; }
.figures { margin: 0; display: grid; gap: 8px; }
.figures dt { color: var(--muted); font-size: 13px; }
.figures dd { margin: 0; font-size: 20px; font-weight: 600; }

/* Map area */
.map-area { flex: 1; min-width: 0; position: relative; background: #eef1f4; }

.notices {
  position: absolute; top: 56px; left: 50%; transform: translateX(-50%);
  display: flex; flex-direction: column; gap: 6px; z-index: 15; max-width: min(560px, 90%);
}
.notice {
  display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: 6px;
  background: var(--surface); border: 1px solid var(--line); box-shadow: 0 1px 4px rgb(0 0 0 / 15%);
}
.notice-warning { border-color: var(--warning); }
.notice button { border: 0; background: transparent; color: var(--accent); }

.about { border: 0; border-radius: 10px; padding: 24px; max-width: 520px; }
.about::backdrop { background: rgb(15 23 42 / 50%); }

/* Narrow screens: the panel becomes a full-height sheet over the map. */
@media (max-width: 899px) {
  .panel { position: absolute; left: var(--rail-width); right: 0; top: 0; bottom: 0; width: auto !important; }
  .panel-resize { display: none; }
}
```

- [ ] **Step 9: Run to verify pass**

Run: `npm --prefix frontend run e2e -- frame.spec.ts`
Expected: 10 passed

Run: `npm --prefix frontend run build`
Expected: type-check and build succeed with no errors

- [ ] **Step 10: Commit**

```bash
git add frontend
git commit -m "feat(frontend): app frame, icon rail and section panel"
```

---

### Task 10: The map

**Files:**
- Create: `frontend/src/components/MapView.tsx`
- Create: `frontend/src/data/useLayerProbes.ts`
- Modify: `frontend/src/App.tsx`, `frontend/src/styles.css`
- Test: `frontend/e2e/map.spec.ts`

**Interfaces:**
- Consumes: `PortalData`, `tileUrlTemplate`, `probeTile`, `clickTarget`, `effectiveYear`, both stores.
- Produces: `<MapView data={data} />`, which fills `.map-area` and marks itself `data-map-ready="true"` once the map has loaded; `useLayerProbes(catalogue)`, which sets or clears `uiStore.layerErrors[id]` for every active layer.
- Map layer ids: `districts-fill`, `districts-line`, `selected-district`, `provinces-line`, `selected-province`. A data layer's source and layer both use the id `data-<layer id>`.
- MapLibre API to check against its documentation if a call does not type-check: `Map`, `NavigationControl`, `Popup`, `addSource`, `addLayer`, `moveLayer`, `setFilter`, `setFeatureState`, `setPaintProperty`, `setLayoutProperty`, `fitBounds`.

- [ ] **Step 1: Write the failing end-to-end tests**

`frontend/e2e/map.spec.ts`:

```ts
import { expect, test } from '@playwright/test'
import { mockTiles, openPortal } from './helpers'

test('the map starts and reports ready', async ({ page }) => {
  await openPortal(page)
  await expect(page.locator('[data-map-ready="true"]')).toBeVisible()
})

test('falls back to a plain background when the background map is unreachable', async ({ page }) => {
  await mockTiles(page)
  await page.route('https://basemap.test/**', (route) => route.abort())
  await page.goto('/')
  await expect(page.getByText('Background map unavailable')).toBeVisible()
  await expect(page.locator('[data-map-ready="true"]')).toBeVisible()
})

test('still starts when boundaries are not loaded', async ({ page }) => {
  await page.route('**/api/places/boundaries**', (route) =>
    route.fulfill({ status: 404, json: { detail: { message: 'none', reason: 'no-data' } } }),
  )
  await openPortal(page)
  await expect(page.locator('[data-map-ready="true"]')).toBeVisible()
})

test('requests tiles for an active layer, with the year when the layer has years', async ({ page }) => {
  const requested: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/tiles/')) requested.push(request.url())
  })
  await openPortal(page)
  await page.locator('[data-map-ready="true"]').waitFor()
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await page.getByRole('switch', { name: 'Fake yearly' }).check()
  await expect.poll(() => requested.some((url) => /fake-yearly\/\d+\/\d+\/\d+\?year=2010/.test(url))).toBe(true)
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npm --prefix frontend run e2e -- map.spec.ts`
Expected: FAIL, `[data-map-ready="true"]` never appears

- [ ] **Step 3: Layer probes**

`frontend/src/data/useLayerProbes.ts`:

```ts
import { useEffect, useRef } from 'react'
import { probeTile } from '../api/client'
import type { Catalogue } from '../api/types'
import { effectiveYear } from '../state/selectors'
import { uiStore, useUi } from '../state/uiState'
import { useView } from '../state/viewState'

/**
 * Checks that each active layer's tiles can be served, and flags the layer if not.
 * A layer is re-checked when its displayed year changes or the user presses Retry.
 */
export function useLayerProbes(catalogue: Catalogue): void {
  const layers = useView((s) => s.layers)
  const year = useView((s) => s.year)
  const retryCounts = useUi((s) => s.retryCounts)
  const probed = useRef(new Map<string, string>())

  useEffect(() => {
    const ui = uiStore.getState()
    const activeIds = new Set(layers.map((l) => l.id))
    for (const id of [...probed.current.keys()]) {
      if (!activeIds.has(id)) {
        probed.current.delete(id)
        ui.forgetLayer(id)
      }
    }
    for (const active of layers) {
      const layer = catalogue.layers.find((l) => l.id === active.id)
      if (!layer) continue
      const shownYear = effectiveYear(layer.years, year)
      const retry = retryCounts[layer.id] ?? 0
      const key = `${shownYear ?? ''}|${retry}`
      if (probed.current.get(layer.id) === key) continue
      probed.current.set(layer.id, key)
      probeTile(layer.id, shownYear, retry).then((ok) => {
        if (probed.current.get(layer.id) !== key) return
        if (ok) uiStore.getState().clearLayerError(layer.id)
        else uiStore.getState().setLayerError(layer.id)
      })
    }
  }, [layers, year, retryCounts, catalogue])
}
```

- [ ] **Step 4: The map component**

`frontend/src/components/MapView.tsx`:

```tsx
import maplibregl, { type Map as MapLibreMap, type StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import { tileUrlTemplate } from '../api/client'
import { COUNTRY_ID, type Layer } from '../api/types'
import type { PortalData } from '../data/usePortalData'
import { clickTarget, effectiveYear } from '../state/selectors'
import { uiStore, useUi } from '../state/uiState'
import { useView, viewStore } from '../state/viewState'

const BLANK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#eef1f4' } }],
}

const dataId = (layerId: string) => `data-${layerId}`

/** Use the online background map if it answers, otherwise a plain background. */
async function resolveStyle(url: string): Promise<{ style: string | StyleSpecification; fallback: boolean }> {
  try {
    const response = await fetch(url)
    if (!response.ok) throw new Error(String(response.status))
    return { style: url, fallback: false }
  } catch {
    return { style: BLANK_STYLE, fallback: true }
  }
}

function addBoundaries(map: MapLibreMap, data: PortalData) {
  const { province, district } = data.boundaries
  if (district) {
    map.addSource('districts', { type: 'geojson', data: district, promoteId: 'id' })
    map.addLayer({
      id: 'districts-fill',
      type: 'fill',
      source: 'districts',
      paint: {
        'fill-color': '#1d4ed8',
        'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.15, 0],
      },
    })
    map.addLayer({
      id: 'districts-line', type: 'line', source: 'districts',
      paint: { 'line-color': '#64748b', 'line-width': 0.5 },
    })
  }
  if (province) {
    map.addSource('provinces', { type: 'geojson', data: province, promoteId: 'id' })
    map.addLayer({
      id: 'provinces-line', type: 'line', source: 'provinces',
      paint: { 'line-color': '#334155', 'line-width': 1.5 },
    })
    map.addLayer({
      id: 'selected-province', type: 'line', source: 'provinces',
      filter: ['==', ['get', 'id'], ''],
      paint: { 'line-color': '#0f172a', 'line-width': 2.5 },
    })
  }
  if (district) {
    map.addLayer({
      id: 'selected-district', type: 'line', source: 'districts',
      filter: ['==', ['get', 'id'], ''],
      paint: { 'line-color': '#1d4ed8', 'line-width': 3 },
    })
  }
}

function wireInteractions(map: MapLibreMap, data: PortalData) {
  if (!map.getLayer('districts-fill')) return
  let hovered: string | null = null
  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false })
  const clearHover = () => {
    if (hovered) map.setFeatureState({ source: 'districts', id: hovered }, { hover: false })
    hovered = null
  }

  map.on('mousemove', 'districts-fill', (event) => {
    const feature = event.features?.[0]
    if (!feature) return
    const id = String(feature.properties.id)
    if (hovered !== id) {
      clearHover()
      hovered = id
      map.setFeatureState({ source: 'districts', id }, { hover: true })
    }
    map.getCanvas().style.cursor = 'pointer'
    popup.setLngLat(event.lngLat).setText(String(feature.properties.name)).addTo(map)
  })
  map.on('mouseleave', 'districts-fill', () => {
    clearHover()
    map.getCanvas().style.cursor = ''
    popup.remove()
  })
  map.on('click', 'districts-fill', (event) => {
    const feature = event.features?.[0]
    if (!feature) return
    const target = clickTarget(data.places, viewStore.getState().place, String(feature.properties.id))
    if (target) viewStore.getState().selectPlace(target)
  })
}

function addDataLayer(map: MapLibreMap, layer: Layer, year: number | null, retry: number) {
  const id = dataId(layer.id)
  const tiles = [`${window.location.origin}${tileUrlTemplate(layer.id, year, retry)}`]
  if (layer.kind === 'vector') {
    const colour = layer.legend?.type === 'classes' ? layer.legend.items[0].colour : '#1d4ed8'
    map.addSource(id, { type: 'vector', tiles })
    map.addLayer({ id, type: 'fill', source: id, 'source-layer': layer.id, paint: { 'fill-color': colour } })
  } else {
    map.addSource(id, { type: 'raster', tiles, tileSize: 256 })
    map.addLayer({ id, type: 'raster', source: id })
  }
}

function removeDataLayer(map: MapLibreMap, layerId: string) {
  const id = dataId(layerId)
  if (map.getLayer(id)) map.removeLayer(id)
  if (map.getSource(id)) map.removeSource(id)
}

/** Data layers sit under every boundary layer, so borders stay readable. */
function boundaryAnchor(map: MapLibreMap): string | undefined {
  return ['districts-fill', 'provinces-line'].find((id) => map.getLayer(id))
}

export function MapView({ data }: { data: PortalData }) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const built = useRef(new Map<string, string>())
  const [ready, setReady] = useState(false)
  const layers = useView((s) => s.layers)
  const place = useView((s) => s.place)
  const year = useView((s) => s.year)
  const retryCounts = useUi((s) => s.retryCounts)

  useEffect(() => {
    let cancelled = false
    let map: MapLibreMap | null = null
    const builtLayers = built.current
    const country = data.places.find((p) => p.id === COUNTRY_ID)

    resolveStyle(data.catalogue.basemap_style_url).then(({ style, fallback }) => {
      if (cancelled || !container.current) return
      if (fallback) {
        uiStore.getState().addNotice('Background map unavailable. Data is shown on a plain background.')
      }
      try {
        map = new maplibregl.Map({
          container: container.current,
          style,
          bounds: country?.bbox,
          fitBoundsOptions: { padding: 24 },
        })
      } catch {
        uiStore.getState().addNotice('The map could not start in this browser.')
        return
      }
      const created = map
      created.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
      created.on('load', () => {
        if (cancelled) return
        addBoundaries(created, data)
        wireInteractions(created, data)
        mapRef.current = created
        setReady(true)
      })
      // Best effort: flag a layer whose tiles start failing after its first check passed.
      created.on('error', (event) => {
        const sourceId = (event as { sourceId?: string }).sourceId
        if (sourceId?.startsWith('data-')) uiStore.getState().setLayerError(sourceId.slice(5))
      })
    })

    return () => {
      cancelled = true
      map?.remove()
      mapRef.current = null
      builtLayers.clear()
      setReady(false)
    }
  }, [data])

  // Outline the selection and move the map to it.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const selected = data.places.find((p) => p.id === place)
    const provinceId = selected?.level === 'district' ? selected.parent_id ?? '' : selected?.id ?? ''
    const districtId = selected?.level === 'district' ? selected.id : ''
    if (map.getLayer('selected-province')) map.setFilter('selected-province', ['==', ['get', 'id'], provinceId])
    if (map.getLayer('selected-district')) map.setFilter('selected-district', ['==', ['get', 'id'], districtId])
    const target = selected ?? data.places.find((p) => p.id === COUNTRY_ID)
    if (target) map.fitBounds(target.bbox, { padding: 48, duration: 600 })
  }, [ready, place, data])

  // Keep the map's data layers in step with the active layers list.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const wanted = new Map<string, string>()
    for (const active of layers) {
      const layer = data.catalogue.layers.find((l) => l.id === active.id)
      if (layer) wanted.set(layer.id, `${effectiveYear(layer.years, year) ?? ''}|${retryCounts[layer.id] ?? 0}`)
    }
    for (const [id, key] of [...built.current]) {
      if (wanted.get(id) !== key) {
        removeDataLayer(map, id)
        built.current.delete(id)
      }
    }
    const anchor = boundaryAnchor(map)
    // Bottom of the list first: each layer is placed just under the boundaries,
    // so later (higher) layers end up above earlier ones.
    for (const active of [...layers].reverse()) {
      const layer = data.catalogue.layers.find((l) => l.id === active.id)
      if (!layer) continue
      if (!built.current.has(layer.id)) {
        addDataLayer(map, layer, effectiveYear(layer.years, year), retryCounts[layer.id] ?? 0)
        built.current.set(layer.id, wanted.get(layer.id)!)
      }
      const id = dataId(layer.id)
      map.moveLayer(id, anchor)
      map.setLayoutProperty(id, 'visibility', active.hidden ? 'none' : 'visible')
      map.setPaintProperty(id, layer.kind === 'vector' ? 'fill-opacity' : 'raster-opacity', active.opacity)
    }
  }, [ready, layers, year, retryCounts, data])

  return <div ref={container} className="map" data-map-ready={ready} />
}
```

- [ ] **Step 5: Mount the map**

In `frontend/src/App.tsx`, add the imports:

```tsx
import { MapView } from './components/MapView'
import { useLayerProbes } from './data/useLayerProbes'
```

In `Portal`, add `useLayerProbes(data.catalogue)` on the line after `useUrlSync(...)`, and change `<main>` to:

```tsx
      <main className="map-area">
        <MapView data={data} />
        <Notices />
      </main>
```

Append to `frontend/src/styles.css`:

```css
.map { position: absolute; inset: 0; }
```

- [ ] **Step 6: Run to verify pass**

Run: `npm --prefix frontend run e2e`
Expected: map.spec.ts 4 passed; frame.spec.ts still 10 passed

If the map never becomes ready in headless Chromium, add `launchOptions: { args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] }` under `use` in `playwright.config.ts` and re-run.

- [ ] **Step 7: Check by hand**

Run `npm run dev`. With the real catalogue there are no ready layers, so check: the background map draws; the zoom buttons work; if Task 5 is done, hovering a district highlights it and shows its name, a first click outlines the province, a second click inside it outlines the district, and a click in another province switches to that province. Stop the servers.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat(frontend): map with boundaries, selection and data layers"
```

---

### Task 11: Active layers list, legend and time slider

**Files:**
- Create: `frontend/src/components/ActiveLayers.tsx`, `Legend.tsx`, `TimeSlider.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/styles.css`
- Test: `frontend/e2e/layers.spec.ts`

**Interfaces:**
- Consumes: `Catalogue`, both stores, `timeRange`, `effectiveYear`.
- Produces: `<ActiveLayers catalogue />` (a region labelled "Active layers", rendered only when a layer is active), `<Legend catalogue />` (a region labelled "Legend", same rule), `<TimeSlider catalogue />` (a group labelled "Year", rendered only when `timeRange` is not null).

- [ ] **Step 1: Write the failing end-to-end tests**

`frontend/e2e/layers.spec.ts`:

```ts
import { expect, test, type Page } from '@playwright/test'
import { mockBasemap, openPortal } from './helpers'

async function switchOn(page: Page, section: string, layer: string) {
  await page.getByRole('button', { name: section }).click()
  await page.getByRole('switch', { name: layer }).check()
}

test('layers from two sections stack in the active list and the legend', async ({ page }) => {
  await openPortal(page)
  await switchOn(page, 'Alpha section', 'Fake yearly')
  await switchOn(page, 'Beta section', 'Fake static')

  const active = page.getByRole('region', { name: 'Active layers' })
  await expect(active.getByRole('listitem')).toHaveText([/Fake static/, /Fake yearly/])
  const legend = page.getByRole('region', { name: 'Legend' })
  await expect(legend.getByRole('heading')).toHaveText([/Fake static/, /Fake yearly/])
  await expect(legend).toContainText('Yearly class')
  await expect(legend).toContainText('0 – 100 %')
})

test('layers can be reordered, faded, hidden and removed', async ({ page }) => {
  await openPortal(page)
  await switchOn(page, 'Alpha section', 'Fake yearly')
  await switchOn(page, 'Beta section', 'Fake static')
  const active = page.getByRole('region', { name: 'Active layers' })

  await active.getByRole('button', { name: 'Move Fake yearly up' }).click()
  await expect(active.getByRole('listitem')).toHaveText([/Fake yearly/, /Fake static/])
  await expect(page.getByRole('region', { name: 'Legend' }).getByRole('heading')).toHaveText([
    /Fake yearly/, /Fake static/,
  ])

  await active.getByRole('slider', { name: 'Opacity of Fake yearly' }).fill('0.4')
  await expect(page).toHaveURL(/fake-yearly:0\.4/)

  await active.getByRole('button', { name: 'Hide Fake yearly' }).click()
  await expect(active.getByRole('button', { name: 'Show Fake yearly' })).toBeVisible()

  await active.getByRole('button', { name: 'Remove Fake static' }).click()
  await expect(active.getByRole('listitem')).toHaveCount(1)
  await expect(page.getByRole('switch', { name: 'Fake static' })).not.toBeChecked()
})

test('the active list and legend disappear when no layer is active', async ({ page }) => {
  await openPortal(page)
  await expect(page.getByRole('region', { name: 'Active layers' })).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'Legend' })).toHaveCount(0)
})

test('the time slider appears only when something on screen has years', async ({ page }) => {
  await openPortal(page)
  const slider = page.getByRole('group', { name: 'Year' })
  await expect(slider).toHaveCount(0)

  await page.getByRole('button', { name: 'Beta section' }).click()
  await page.getByRole('switch', { name: 'Fake static' }).check()
  await expect(slider).toHaveCount(0)

  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(slider).toBeVisible()
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(slider).toHaveCount(0)

  await switchOn(page, 'Alpha section', 'Fake yearly')
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(slider).toBeVisible()
})

test('the time slider steps through years and the legend shows the year on display', async ({ page }) => {
  await openPortal(page)
  await switchOn(page, 'Alpha section', 'Fake yearly')
  const slider = page.getByRole('group', { name: 'Year' })
  const legend = page.getByRole('region', { name: 'Legend' })
  await expect(slider.getByRole('slider')).toHaveValue('2010')
  await expect(legend).toContainText('Fake yearly (2010)')

  await slider.getByRole('button', { name: 'Previous year' }).click()
  await expect(slider.getByRole('slider')).toHaveValue('2009')
  await expect(legend).toContainText('Fake yearly (2009)')
  await expect(page).toHaveURL(/year=2009/)

  await slider.getByRole('button', { name: 'Next year' }).click()
  await expect(slider.getByRole('slider')).toHaveValue('2010')
  await expect(slider.getByRole('button', { name: 'Next year' })).toBeDisabled()
})

test('play steps forward and wraps to the first year', async ({ page }) => {
  await openPortal(page)
  await switchOn(page, 'Alpha section', 'Fake yearly')
  const slider = page.getByRole('group', { name: 'Year' })
  await slider.getByRole('button', { name: 'Play' }).click()
  await expect(slider.getByRole('slider')).toHaveValue('2000', { timeout: 3000 })
  await slider.getByRole('button', { name: 'Pause' }).click()
})

test('a layer whose tiles fail shows a warning and can be retried', async ({ page }) => {
  await mockBasemap(page)
  await page.goto('/')
  await page.getByRole('navigation', { name: 'Sections' }).waitFor()
  await switchOn(page, 'Alpha section', 'Fake yearly')
  const active = page.getByRole('region', { name: 'Active layers' })
  await expect(active.getByText('Could not load')).toBeVisible()

  await page.route('**/api/tiles/**', (route) => route.fulfill({ status: 200, contentType: 'image/png', body: '' }))
  await active.getByRole('button', { name: 'Retry Fake yearly' }).click()
  await expect(active.getByText('Could not load')).toHaveCount(0)
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npm --prefix frontend run e2e -- layers.spec.ts`
Expected: FAIL, the "Active layers" region is not found

- [ ] **Step 3: Active layers list**

`frontend/src/components/ActiveLayers.tsx`:

```tsx
import { ChevronDown, ChevronUp, Eye, EyeOff, RotateCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { Catalogue } from '../api/types'
import { uiStore, useUi } from '../state/uiState'
import { useView, viewStore } from '../state/viewState'

export function ActiveLayers({ catalogue }: { catalogue: Catalogue }) {
  const layers = useView((s) => s.layers)
  const errors = useUi((s) => s.layerErrors)
  const [dragged, setDragged] = useState<string | null>(null)
  if (!layers.length) return null
  const view = viewStore.getState()

  return (
    <section className="active-layers" aria-label="Active layers">
      <h3>Active layers</h3>
      <ul>
        {layers.map((active, index) => {
          const title = catalogue.layers.find((l) => l.id === active.id)?.title ?? active.id
          return (
            <li
              key={active.id}
              draggable
              onDragStart={() => setDragged(active.id)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => {
                if (dragged) view.moveLayer(dragged, index)
                setDragged(null)
              }}
            >
              <div className="active-row">
                <span className="active-title">{title}</span>
                <button
                  type="button" aria-label={`Move ${title} up`} disabled={index === 0}
                  onClick={() => view.moveLayer(active.id, index - 1)}
                >
                  <ChevronUp size={14} />
                </button>
                <button
                  type="button" aria-label={`Move ${title} down`} disabled={index === layers.length - 1}
                  onClick={() => view.moveLayer(active.id, index + 1)}
                >
                  <ChevronDown size={14} />
                </button>
                <button
                  type="button" aria-label={`${active.hidden ? 'Show' : 'Hide'} ${title}`}
                  onClick={() => view.toggleHidden(active.id)}
                >
                  {active.hidden ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
                <button type="button" aria-label={`Remove ${title}`} onClick={() => view.removeLayer(active.id)}>
                  <Trash2 size={14} />
                </button>
              </div>
              <input
                type="range" min={0} max={1} step={0.05} value={active.opacity}
                aria-label={`Opacity of ${title}`}
                onChange={(event) => view.setOpacity(active.id, Number(event.target.value))}
              />
              {errors[active.id] && (
                <div className="active-error">
                  <span>Could not load</span>
                  <button
                    type="button" aria-label={`Retry ${title}`}
                    onClick={() => uiStore.getState().retryLayer(active.id)}
                  >
                    <RotateCw size={12} /> Retry
                  </button>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
```

- [ ] **Step 4: Legend**

`frontend/src/components/Legend.tsx`:

```tsx
import type { Catalogue, Legend as LegendSpec } from '../api/types'
import { effectiveYear } from '../state/selectors'
import { useView } from '../state/viewState'

function Key({ legend }: { legend: LegendSpec }) {
  if (legend.type === 'classes') {
    return (
      <ul className="legend-classes">
        {legend.items.map((item) => (
          <li key={item.label}>
            <span className="legend-swatch" style={{ background: item.colour }} />
            {item.label}
          </li>
        ))}
      </ul>
    )
  }
  return (
    <div className="legend-ramp">
      <span className="legend-bar" style={{ background: `linear-gradient(to right, ${legend.colours.join(', ')})` }} />
      <span>
        {legend.min} – {legend.max} {legend.unit}
      </span>
    </div>
  )
}

export function Legend({ catalogue }: { catalogue: Catalogue }) {
  const layers = useView((s) => s.layers)
  const year = useView((s) => s.year)
  if (!layers.length) return null

  return (
    <section className="legend" aria-label="Legend">
      {layers.map((active) => {
        const layer = catalogue.layers.find((l) => l.id === active.id)
        if (!layer?.legend) return null
        const shownYear = effectiveYear(layer.years, year)
        return (
          <div key={layer.id} className={active.hidden ? 'legend-entry legend-hidden' : 'legend-entry'}>
            <h4>{shownYear === null ? layer.title : `${layer.title} (${shownYear})`}</h4>
            <Key legend={layer.legend} />
          </div>
        )
      })}
    </section>
  )
}
```

- [ ] **Step 5: Time slider**

`frontend/src/components/TimeSlider.tsx`:

```tsx
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { Catalogue } from '../api/types'
import { timeRange } from '../state/selectors'
import { emptyView, useView, viewStore } from '../state/viewState'

const STEP_MS = 1000

export function TimeSlider({ catalogue }: { catalogue: Catalogue }) {
  const section = useView((s) => s.section)
  const layers = useView((s) => s.layers)
  const year = useView((s) => s.year)
  const [playing, setPlaying] = useState(false)
  const range = useMemo(() => timeRange({ ...emptyView, section, layers }, catalogue), [section, layers, catalogue])

  const first = range?.first ?? 0
  const last = range?.last ?? 0
  const current = Math.min(last, Math.max(first, year ?? last))

  useEffect(() => {
    if (!range) setPlaying(false)
  }, [range])

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => {
      const now = viewStore.getState().year ?? last
      viewStore.getState().setYear(now >= last ? first : now + 1)
    }, STEP_MS)
    return () => window.clearInterval(timer)
  }, [playing, first, last])

  if (!range) return null
  const setYear = (value: number) => viewStore.getState().setYear(Math.min(last, Math.max(first, value)))

  return (
    <div className="time-slider" role="group" aria-label="Year">
      <button type="button" aria-label="Previous year" disabled={current <= first} onClick={() => setYear(current - 1)}>
        <ChevronLeft size={16} />
      </button>
      <span>{first}</span>
      <input
        type="range" min={first} max={last} step={1} value={current} aria-label="Year"
        onChange={(event) => setYear(Number(event.target.value))}
      />
      <span>{last}</span>
      <button type="button" aria-label="Next year" disabled={current >= last} onClick={() => setYear(current + 1)}>
        <ChevronRight size={16} />
      </button>
      <strong>{current}</strong>
      <button type="button" aria-label={playing ? 'Pause' : 'Play'} onClick={() => setPlaying((p) => !p)}>
        {playing ? <Pause size={16} /> : <Play size={16} />}
      </button>
    </div>
  )
}
```

- [ ] **Step 6: Mount and style**

In `frontend/src/App.tsx`, import the three components and change `<main>` to:

```tsx
      <main className="map-area">
        <MapView data={data} />
        <ActiveLayers catalogue={data.catalogue} />
        <Legend catalogue={data.catalogue} />
        <TimeSlider catalogue={data.catalogue} />
        <Notices />
      </main>
```

Append to `frontend/src/styles.css`:

```css
.active-layers, .legend, .time-slider {
  position: absolute; z-index: 10; background: var(--surface);
  border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 1px 4px rgb(0 0 0 / 15%);
}
.active-layers { top: 56px; right: 12px; width: 260px; padding: 10px 12px; }
.active-layers h3 { font-size: 13px; text-transform: uppercase; color: var(--muted); margin-bottom: 6px; }
.active-layers ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.active-layers li { cursor: grab; }
.active-row { display: flex; align-items: center; gap: 2px; }
.active-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.active-row button { border: 0; background: transparent; padding: 4px; border-radius: 4px; }
.active-row button:hover:not(:disabled) { background: #f1f5f9; }
.active-layers input[type='range'] { width: 100%; }
.active-error { display: flex; justify-content: space-between; color: var(--warning); font-size: 13px; }
.active-error button { border: 0; background: transparent; color: var(--accent); }

.legend { left: 12px; bottom: 76px; max-width: 260px; max-height: 40%; overflow-y: auto; padding: 10px 12px; }
.legend-entry + .legend-entry { margin-top: 10px; }
.legend-entry h4 { margin: 0 0 4px; font-size: 13px; }
.legend-hidden { opacity: 0.45; }
.legend-classes { list-style: none; margin: 0; padding: 0; font-size: 13px; }
.legend-classes li { display: flex; align-items: center; gap: 6px; }
.legend-swatch { width: 14px; height: 14px; border-radius: 3px; border: 1px solid var(--line); }
.legend-ramp { display: grid; gap: 2px; font-size: 13px; }
.legend-bar { height: 10px; border-radius: 3px; border: 1px solid var(--line); }

.time-slider {
  left: 12px; right: 12px; bottom: 12px; display: flex; align-items: center; gap: 10px; padding: 10px 14px;
}
.time-slider input[type='range'] { flex: 1; }
.time-slider button { border: 0; background: transparent; padding: 4px; }
.time-slider button:disabled { opacity: 0.35; cursor: default; }
```

- [ ] **Step 7: Run to verify pass**

Run: `npm --prefix frontend run e2e`
Expected: layers.spec.ts 7 passed; earlier specs unchanged

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat(frontend): active layers list, legend and time slider"
```

---

### Task 12: Place search and breadcrumb

**Files:**
- Create: `frontend/src/components/PlaceSearch.tsx`, `Breadcrumb.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/styles.css`
- Test: `frontend/e2e/places.spec.ts`

**Interfaces:**
- Consumes: `Place`, `searchPlaces`, `ancestors`, the view store.
- Produces: `<PlaceSearch places />` (a search box labelled "Search place"), `<Breadcrumb places />` (a navigation labelled "Selected place"). Both sit in a `.map-toolbar` bar across the top of the map area.

- [ ] **Step 1: Write the failing end-to-end tests**

`frontend/e2e/places.spec.ts`:

```ts
import { expect, test } from '@playwright/test'
import { openPortal } from './helpers'

test('select a province, then a district, then step back with the breadcrumb', async ({ page }) => {
  await openPortal(page)
  const crumbs = page.getByRole('navigation', { name: 'Selected place' })
  const search = page.getByRole('searchbox', { name: 'Search place' })
  await expect(crumbs.getByRole('listitem')).toHaveText(['Pakistan'])

  await search.fill('alp')
  await page.getByRole('option', { name: /Alpha/ }).click()
  await expect(crumbs.getByRole('listitem')).toHaveText(['Pakistan', 'Alpha'])
  await expect(search).toHaveValue('')

  await search.fill('district one')
  await page.getByRole('option', { name: /District One/ }).click()
  await expect(crumbs.getByRole('listitem')).toHaveText(['Pakistan', 'Alpha', 'District One'])

  await crumbs.getByRole('button', { name: 'Alpha' }).click()
  await expect(crumbs.getByRole('listitem')).toHaveText(['Pakistan', 'Alpha'])
  await crumbs.getByRole('button', { name: 'Pakistan' }).click()
  await expect(crumbs.getByRole('listitem')).toHaveText(['Pakistan'])
})

test('search ignores case and spaces, names the level, and says when nothing matches', async ({ page }) => {
  await openPortal(page)
  const search = page.getByRole('searchbox', { name: 'Search place' })
  await search.fill('  DISTRICT T ')
  await expect(page.getByRole('option')).toHaveText([/District Three.*District in Beta/, /District Two.*District in Alpha/])
  await search.fill('zzz')
  await expect(page.getByText('No places match')).toBeVisible()
  await search.fill('')
  await expect(page.getByRole('option')).toHaveCount(0)
})

test('the figures heading follows the selected place', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(page.getByRole('heading', { name: 'Figures for Pakistan' })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search place' }).fill('beta')
  await page.getByRole('option', { name: /Beta/ }).click()
  await expect(page.getByRole('heading', { name: 'Figures for Beta' })).toBeVisible()
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npm --prefix frontend run e2e -- places.spec.ts`
Expected: FAIL, the "Selected place" navigation is not found

- [ ] **Step 3: Implement**

`frontend/src/components/PlaceSearch.tsx`:

```tsx
import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Place } from '../api/types'
import { searchPlaces } from '../state/selectors'
import { viewStore } from '../state/viewState'

export function PlaceSearch({ places }: { places: Place[] }) {
  const [query, setQuery] = useState('')
  const results = useMemo(() => searchPlaces(places, query), [places, query])
  const names = useMemo(() => new Map(places.map((p) => [p.id, p.name])), [places])

  const choose = (place: Place) => {
    viewStore.getState().selectPlace(place.id)
    setQuery('')
  }
  const describe = (place: Place) =>
    place.level === 'province' ? 'Province' : `District in ${names.get(place.parent_id ?? '') ?? 'Pakistan'}`

  return (
    <div className="place-search">
      <Search size={16} aria-hidden />
      <input
        type="search"
        aria-label="Search place"
        placeholder="Search place…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && results[0]) choose(results[0])
          if (event.key === 'Escape') setQuery('')
        }}
      />
      {query.trim() !== '' && (
        <ul className="place-results" role="listbox" aria-label="Matching places">
          {results.map((place) => (
            <li key={place.id} role="option" aria-selected={false} onClick={() => choose(place)}>
              <strong>{place.name}</strong>
              <small>{describe(place)}</small>
            </li>
          ))}
          {results.length === 0 && <li className="empty">No places match</li>}
        </ul>
      )}
    </div>
  )
}
```

`frontend/src/components/Breadcrumb.tsx`:

```tsx
import { useMemo } from 'react'
import type { Place } from '../api/types'
import { ancestors } from '../state/selectors'
import { useView, viewStore } from '../state/viewState'

export function Breadcrumb({ places }: { places: Place[] }) {
  const placeId = useView((s) => s.place)
  const trail = useMemo(() => ancestors(places, placeId), [places, placeId])

  return (
    <nav className="breadcrumb" aria-label="Selected place">
      <ol>
        {trail.map((place, index) => {
          const isCurrent = index === trail.length - 1
          return (
            <li key={place.id}>
              {isCurrent ? (
                <span aria-current="location">{place.name}</span>
              ) : (
                <button type="button" onClick={() => viewStore.getState().selectPlace(place.id)}>
                  {place.name}
                </button>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
```

- [ ] **Step 4: Mount and style**

In `frontend/src/App.tsx`, import both and add a toolbar as the second child of `<main>`:

```tsx
      <main className="map-area">
        <MapView data={data} />
        <div className="map-toolbar">
          <PlaceSearch places={data.places} />
          <Breadcrumb places={data.places} />
        </div>
        <ActiveLayers catalogue={data.catalogue} />
        <Legend catalogue={data.catalogue} />
        <TimeSlider catalogue={data.catalogue} />
        <Notices />
      </main>
```

Append to `frontend/src/styles.css`:

```css
.map-toolbar {
  position: absolute; top: 12px; left: 12px; right: 12px; z-index: 12;
  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; pointer-events: none;
}
.map-toolbar > * { pointer-events: auto; }

.place-search {
  position: relative; display: flex; align-items: center; gap: 6px; width: 280px; padding: 6px 10px;
  background: var(--surface); border: 1px solid var(--line); border-radius: 8px;
  box-shadow: 0 1px 4px rgb(0 0 0 / 15%);
}
.place-search input { flex: 1; border: 0; outline: 0; font: inherit; min-width: 0; }
.place-results {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0; margin: 0; padding: 4px; list-style: none;
  background: var(--surface); border: 1px solid var(--line); border-radius: 8px;
  box-shadow: 0 4px 12px rgb(0 0 0 / 15%);
}
.place-results li { display: flex; justify-content: space-between; gap: 8px; padding: 6px 8px; border-radius: 4px; }
.place-results li[role='option'] { cursor: pointer; }
.place-results li[role='option']:hover { background: #f1f5f9; }
.place-results small { color: var(--muted); }

.breadcrumb {
  background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 6px 12px;
  box-shadow: 0 1px 4px rgb(0 0 0 / 15%);
}
.breadcrumb ol { display: flex; gap: 6px; list-style: none; margin: 0; padding: 0; }
.breadcrumb li + li::before { content: '›'; margin-right: 6px; color: var(--muted); }
.breadcrumb button { border: 0; background: transparent; color: var(--accent); padding: 0; }
.breadcrumb [aria-current] { font-weight: 600; }
```

The CSS `::before` separator is not part of the list item's text for Playwright's `toHaveText`, so the test's expected texts are the bare names.

- [ ] **Step 5: Run to verify pass**

Run: `npm --prefix frontend run e2e`
Expected: places.spec.ts 3 passed; earlier specs unchanged

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): place search and breadcrumb"
```

---

### Task 13: URL journeys, README and final verification

**Files:**
- Test: `frontend/e2e/url.spec.ts`
- Modify: `README.md`

**Interfaces:**
- Consumes: every component from Tasks 9 to 12. `useUrlSync` has been mounted since Task 9; this task adds the whole-view journeys that need the search box, the active layers list and the time slider together.

- [ ] **Step 1: Write the whole-view journeys**

`frontend/e2e/url.spec.ts`:

```ts
import { expect, test } from '@playwright/test'
import { openPortal } from './helpers'

test('reloading the page restores the same view', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Beta section' }).click()
  await page.getByRole('switch', { name: 'Fake static' }).check()
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await page.getByRole('switch', { name: 'Fake yearly' }).check()
  const active = page.getByRole('region', { name: 'Active layers' })
  await active.getByRole('button', { name: 'Hide Fake static' }).click()
  await page.getByRole('searchbox', { name: 'Search place' }).fill('district one')
  await page.getByRole('option', { name: /District One/ }).click()
  await page.getByRole('group', { name: 'Year' }).getByRole('button', { name: 'Previous year' }).click()

  await expect(page).toHaveURL(
    /\?section=alpha-section&layers=fake-yearly:0\.8,fake-static:1&hidden=fake-static&place=PK101&year=2009$/,
  )
  await page.reload()

  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeVisible()
  await expect(active.getByRole('listitem')).toHaveText([/Fake yearly/, /Fake static/])
  await expect(active.getByRole('button', { name: 'Show Fake static' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Selected place' }).getByRole('listitem')).toHaveText([
    'Pakistan', 'Alpha', 'District One',
  ])
  await expect(page.getByRole('group', { name: 'Year' }).getByRole('slider')).toHaveValue('2009')
})

test('a plain address stays plain', async ({ page }) => {
  await openPortal(page)
  await expect(page).toHaveURL(/127\.0\.0\.1:5183\/$/)
})

test('invalid values in a link are dropped with a notice and the rest loads', async ({ page }) => {
  await openPortal(page, '/?section=alpha-section&layers=ghost:1,fake-static:9&place=XX&year=1800')
  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Active layers' }).getByRole('listitem')).toHaveText([/Fake static/])
  const notice = page.getByText(/Ignored from the link/)
  await expect(notice).toContainText('layer "ghost"')
  await expect(notice).toContainText('opacity "9" for layer "fake-static"')
  await expect(notice).toContainText('place "XX"')
  await expect(notice).toContainText('year "1800"')
  await expect(page).toHaveURL(/\?section=alpha-section&layers=fake-static:1$/)
})
```

- [ ] **Step 2: Run them**

Run: `npm --prefix frontend run e2e -- url.spec.ts`
Expected: 3 passed. These combine parts that were each built test-first, so they should pass as written. If one fails, the fault is in how two parts interact: fix the code, not the test.

- [ ] **Step 3: Run every suite**

Run: `npm test` at the repo root
Expected: pytest all passed; Vitest all passed; Playwright all passed with none skipped

Run: `npm --prefix frontend run build`
Expected: no type errors

- [ ] **Step 4: Write the README**

Replace the empty `README.md`:

```markdown
# Climate Smart Agriculture Portal

A map-first portal for Pakistan's climate smart agriculture data, built for disaster management stakeholders.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Node 20 or later.

    uv sync
    npm install
    npm --prefix frontend install
    npm run dev

The portal opens in your browser. The backend runs on port 8000 and the frontend on 5173. The background map needs internet access.

## Test it

    npm test

This runs the backend tests (pytest), the frontend logic tests (Vitest) and the browser tests (Playwright). The first time, install the test browser with `npm --prefix frontend exec playwright install chromium`.

## Layout

- `backend/` — FastAPI app. `catalogue.json` describes every section and layer; the interface is built from it.
- `backend/boundaries/` — province and district boundaries, produced by `backend/scripts/prepare_boundaries.py`.
- `frontend/` — React app.
- `data/` — source datasets.
- `docs/superpowers/specs/` — design documents.

## Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `CSA_CATALOGUE_PATH` | `backend/catalogue.json` | Catalogue file |
| `CSA_BOUNDARIES_DIR` | `backend/boundaries` | Boundary GeoJSON folder |
| `CSA_BASEMAP_STYLE_URL` | OpenFreeMap Positron | Background map style |
```

- [ ] **Step 5: Walk the spec's "Done when" list by hand**

Run `npm run dev` and confirm each line, noting any that fail:

1. The portal starts and opens in the browser.
2. All eight sections open from the rail; six say "Data not loaded yet", hazards and exposure say "Coming soon" with their summary.
3. If Task 5 is done: districts highlight on hover, a click selects the province, a second click the district, the search finds both, and the breadcrumb steps back. If Task 5 is not done: the "Boundaries are not loaded" notice shows and everything else works.
4. Stop the backend only (close its process): within one action the "lost its data service" banner appears and the view stays on screen. Restart it and press "Check again".
5. Stop everything, start only the frontend (`npm --prefix frontend run dev`): the full-screen message appears with the start command.
6. Disconnect from the internet and reload: the plain-background notice appears and the boundaries still draw.
7. Resize the window below 900 pixels wide and open a section: the panel covers the map and the close button works.

Layer stacking, the time slider and URL restore need ready layers, which the real catalogue does not have until sub-project 2. They are covered by the Playwright suite against the test catalogue. To see them by hand, start the backend with the fixture catalogue:

PowerShell:

    $env:CSA_CATALOGUE_PATH = "backend/tests/fixtures/test_catalogue.json"; $env:CSA_BOUNDARIES_DIR = "backend/tests/fixtures/boundaries"; npm run dev

The fake layers will show "Could not load", which is correct: the fixture backend has no tiles to serve.

- [ ] **Step 6: Commit**

```bash
git add README.md frontend
git commit -m "test(frontend): whole-view URL journeys; add README"
```

---

## Not in this plan

- Real tile and section data providers (sub-projects 2 and 3). The seams are `tile_providers` and `section_providers` on `create_app`.
- Chart rendering (sub-project 3). The Charts block shows its empty state.
- Hazard and exposure data (sub-project 4).
- Visual design. Styling here is functional; a design pass follows once the shell works.

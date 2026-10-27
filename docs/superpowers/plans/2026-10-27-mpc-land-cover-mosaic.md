# Land Classification Served from Planetary Computer: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every land-classification map layer for all of Pakistan that MPC can provide is drawn by the browser straight from Microsoft Planetary Computer (MPC), one mosaic per year, so the forest, shrub-land and bare-land rasters on this PC are no longer served.

**Architecture:** For each year the backend already searches the MPC catalogue and checks that the year's 11 items cover the whole country (`MpcLandCoverResolver`). It now registers one MPC mosaic over exactly those item ids. From that mosaic id it builds a tile URL template for every `tile_source: "mpc"` layer in the catalogue. The colormap for each template comes from that layer's legend: the full legend for the annual map, or a single entry for a one-class view. The browser fetches the PNG tiles from `planetarycomputer.microsoft.com` directly. The backend serves only the small `/api/land-cover/observation` JSON, and per-place statistics stay in the prepared `backend/data/land_cover_annual.json`.

**Tech Stack:** FastAPI + httpx (backend), MapLibre + React + TypeScript (frontend), MPC Data API (titiler-pgstac `mosaic/register`, `mosaic/{id}/tiles`), pytest, vitest, Playwright.

**Spec:** the user request on 2026-10-27, as follows. The notebook `notebooks/lulc_mpc_tiles_preview_(3).ipynb` uses the MPC-hosted `io-lulc-annual-v02` tiles and statistics. The request is to serve land classification for the whole of Pakistan directly from MPC instead of from data downloaded to this PC. The user chose to "Replace with MPC classes": forest, shrub land and bare land become single-class views of the MPC mosaic, and Crops and Built area are added. Irrigated/rainfed has no MPC equivalent, so it stays local for a later follow-up.

## Findings this plan rests on (verified live on 2026-10-27)

- **Bug in today's map:** `/api/land-cover/observation` returns 11 per-item tile templates, and `MapView.tsx:237` passes them as one source's `tiles` array. MapLibre treats that array as mirrors of the same tileset, not as a mosaic, so each map tile is fetched from an arbitrary item and the country draws patchily.
- `POST https://planetarycomputer.microsoft.com/api/data/v1/mosaic/register` with body `{"collections":["io-lulc-annual-v02"],"filter-lang":"cql2-json","filter":{"op":"in","args":[{"property":"id"},[...item ids...]]}}` returns `{"searchid": "pc1.<digits>.<hex>", ...}`. Re-registering the same body returns a **new** id, so the id must be cached per year.
- `GET .../mosaic/{searchid}/tiles/WebMercatorQuad/{z}/{x}/{y}@1x.png?collection=io-lulc-annual-v02&assets=data&colormap=<json>` returns RGBA PNGs in 0.4–2.2 s for z4–z12, with `Cache-Control: public, max-age=3600`. A tile outside the items returns `404 {"error":{"code":"ResourceNotFound"}}`. The URL needs no SAS token.
- A one-entry colormap such as `{"2":[57,125,73,255]}` draws only that class; every other pixel is `(0,0,0,0)`. Pixel counts match the full map exactly.
- Filtering by a datetime *instant* matches nothing, and a whole-year interval also matches the previous year's items, whose `end_datetime` is 1 January. The explicit `id IN [...]` filter is exact, and the resolver already knows the ids.
- The MPC `/statistics` endpoint is **not** used: it returned 502 in the notebook, and it counts against the item's extent rather than the place. The prepared statistics already come from MPC over HTTP (`prepare_land_cover_stats.py`) and stay as they are.

## Global Constraints

- Collection `io-lulc-annual-v02`, years 2017–2023 (`SUPPORTED_YEARS`); MPC class codes are exactly `{1, 2, 4, 5, 7, 8, 9, 10, 11}`.
- Tile host must be `https://planetarycomputer.microsoft.com/`; tile URLs never carry SAS parameters (`sig`, `se`, `sp`, `sv`, …).
- Tile templates keep literal `{z}/{x}/{y}` for MapLibre; only query values are percent-encoded.
- Class colours are the MPC `io-lulc-9-class` colours already in the `annual-land-cover` legend (Trees `#397d49`, Crops `#e49635`, Built area `#c4281b`, Bare ground `#a59b8f`, Rangeland `#e3e2c3`).
- Attribution string unchanged: `Esri / Impact Observatory / Microsoft Planetary Computer`.
- Never stop processes by port on this machine. Run e2e only after checking that 8010/5183 are free.
- Deleting the retired `.tif` files is the user's action; the plan does not delete files on disk.
- Work on a new branch `feat/mpc-land-mosaic` off `feat/portal-data`; file a GitHub issue for it first (`gh issue create`, label `ready-for-agent`).

## Review Focus

1. **An old shared link names a retired layer** (`?layers=forest:0.8,irrigated-rainfed:1`): the retired layer is dropped with the existing "invalid values" notice, and the rest of the link loads. Test: Task 3, Step 5.
2. **Two MPC layers on at once** (annual map + Trees): one observation request per year, and both layers are drawn from that same year's mosaic. Test: Task 2, Step 7.
3. **MPC mosaic registration fails or answers garbage** (503, timeout, missing or odd `searchid`): the error codes `upstream-unavailable`, `upstream-timeout` and `invalid-upstream-response` reach the existing observation error mapping, and the layer shows "Could not load" with a retry, not a silently blank map. Test: Task 1, Step 1.
4. **Colormap encoding breaks the template** (JSON quotes and braces in the query): the template keeps literal `{z}/{x}/{y}`, and the `colormap` query value parses back to the legend's classes. Test: Task 1, Step 1.
5. **A catalogue typo gives an MPC layer a class MPC does not have** (e.g. `"3"`) or no legend: catalogue loading fails at startup with a clear message, instead of drawing an empty layer. Test: Task 2, Step 1.

---

### Task 1: Resolver registers one mosaic per year

**Files:**
- Modify: `backend/csa_portal/land_cover_mpc.py` (`ResolvedLandCover`, `MpcLandCoverResolver._tile_template`, `_resolve`)
- Test: `backend/tests/test_land_cover_mpc.py`

**Interfaces:**
- Produces:
  - `ResolvedLandCover` fields: `year: int, collection: str, version: str, item_ids: tuple[str, ...], search_id: str, bounds: tuple[float, float, float, float], attribution: str, expires_at: float`. `tile_templates` is removed.
  - `def mosaic_tile_url(search_id: str, colormap: Mapping[int, str]) -> str`: a module-level pure function. `colormap` maps an MPC class code to `#rrggbb`.
  - `MpcLandCoverResolver._register_mosaic(item_ids: tuple[str, ...]) -> str`: one `POST {TILE_API}/mosaic/register` through the existing `_json`.

- [ ] **Step 1: Write the failing tests** (replace the per-item template tests; keep the search, coverage and caching tests)

```python
def test_resolve_registers_one_mosaic_over_exactly_the_years_items():
    # handler: /search → items 42Q-2018, 42Q-2019, 43Q-2019; /mosaic/register → {"searchid": "pc1.1.abc"}
    result = resolver(handler).resolve(2019)
    assert result.search_id == "pc1.1.abc"
    assert result.item_ids == ("42Q-2019", "43Q-2019")
    register = [r for r in seen if r.url.path.endswith("/mosaic/register")]
    assert len(register) == 1
    body = json.loads(register[0].content)
    assert body["filter"] == {"op": "in", "args": [{"property": "id"}, ["42Q-2019", "43Q-2019"]]}
    assert body["collections"] == [COLLECTION]
    assert not any("tilejson" in str(r.url) for r in seen)

def test_a_cached_year_does_not_register_again():   # two resolve(2019) calls within the TTL → one register request

@pytest.mark.parametrize("status, code", [(503, "upstream-unavailable"), (429, "upstream-unavailable"), (400, "upstream-rejected")])
def test_a_failed_registration_has_a_stable_error_code(status, code): ...

@pytest.mark.parametrize("body", [{}, {"searchid": ""}, {"searchid": 7}, {"searchid": "../../x"}, {"searchid": "a b"}])
def test_an_unusable_search_id_is_an_invalid_upstream_response(body): ...   # code == "invalid-upstream-response"

def test_mosaic_tile_url_keeps_placeholders_and_encodes_the_colormap():
    url = mosaic_tile_url("pc1.1.abc", {2: "#397d49", 5: "#e49635"})
    assert url.startswith("https://planetarycomputer.microsoft.com/api/data/v1/mosaic/pc1.1.abc/tiles/WebMercatorQuad/{z}/{x}/{y}@1x.png?")
    query = dict(parse_qsl(urlsplit(url).query))
    assert query["collection"] == COLLECTION and query["assets"] == "data"
    assert json.loads(query["colormap"]) == {"2": [57, 125, 73, 255], "5": [228, 150, 53, 255]}
    assert not {"sig", "se", "sp", "sv"} & set(query)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest backend/tests/test_land_cover_mpc.py -q`
Expected: FAIL (`ImportError: cannot import name 'mosaic_tile_url'`)

- [ ] **Step 3: Implement**

In `_resolve`, call `_register_mosaic(item_ids)` once, after `_items(year)`, in place of the per-item `_tile_template` loop. Delete `_tile_template` and its credential and host checks: the URL is now built locally, so those checks have nothing to guard. Accept a `searchid` only when it is a `str` matching `^[A-Za-z0-9._-]{1,128}$`. `mosaic_tile_url` uses `urlencode` for the query: `collection`, `assets=data`, and `colormap=json.dumps({str(code): [r, g, b, 255]}, separators=(",", ":"))`, with the codes sorted. Append the query to the literal path, so the placeholders stay unencoded.

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest backend/tests/test_land_cover_mpc.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/csa_portal/land_cover_mpc.py backend/tests/test_land_cover_mpc.py
git commit -m "feat: resolve each land-cover year to one MPC mosaic"
```

---

### Task 2: The observation hands out one tile URL per MPC layer, and the map draws it

**Files:**
- Modify: `backend/csa_portal/catalogue.py` (`Layer` validation for `tile_source == "mpc"`)
- Modify: `backend/csa_portal/main.py:332-363` (`land_cover_observation`)
- Modify: `frontend/src/api/types.ts:80-87` (`LandCoverObservation`)
- Modify: `frontend/src/components/MapView.tsx:232-242` (`addDataLayer`, the `mpc` branch)
- Test: `backend/tests/test_catalogue.py`, `backend/tests/test_land_cover_observation.py`, `frontend/src/api/client.test.ts`, `frontend/e2e/observations.spec.ts`

**Interfaces:**
- Consumes: `ResolvedLandCover.search_id` and `mosaic_tile_url(search_id, colormap)` from Task 1.
- Produces:
  - Observation JSON: `{year, collection, search_id, item_ids, tiles: {<layer_id>: <template>}, bounds, attribution}`. `tiles` has one entry for every catalogue layer with `tile_source == "mpc"`, and `tile_urls` is removed.
  - TS: `interface LandCoverObservation { year: number; collection: string; search_id: string; item_ids: string[]; tiles: Record<string, string>; bounds: [number, number, number, number]; attribution: string }`.
  - `MPC_CLASS_CODES: frozenset[int] = frozenset({1, 2, 4, 5, 7, 8, 9, 10, 11})` in `land_cover_mpc.py`, imported by `catalogue.py`.

- [ ] **Step 1: Write the failing catalogue test** (`test_catalogue.py`)

```python
@pytest.mark.parametrize("legend, message", [
    (None, "needs a classes legend"),
    ({"type": "classes", "items": [{"colour": "#123456", "label": "Shrub", "value": "3"}]}, "not an MPC class: 3"),
    ({"type": "classes", "items": [{"colour": "green", "label": "Trees", "value": "2"}]}, "#rrggbb"),
])
def test_an_mpc_layer_must_colour_real_mpc_classes(legend, message):
    with pytest.raises(ValidationError, match=message):
        Catalogue.model_validate(catalogue_with(mpc_layer(legend=legend)))
```

An MPC layer also needs `years`. Add the matching case `(years=None) → "needs years"`.

- [ ] **Step 2: Write the failing observation tests** (`test_land_cover_observation.py`)

Update the fake resolver to return `search_id="pc1.1.abc"`, then rewrite the existing `tile_urls` assertions:

```python
def test_the_observation_gives_every_mpc_layer_its_own_template():
    body = client.get("/api/land-cover/observation?year=2019").json()
    assert set(body["tiles"]) == {"annual-land-cover", "trees"}   # the test catalogue holds these two MPC layers
    trees = dict(parse_qsl(urlsplit(body["tiles"]["trees"]).query))
    assert json.loads(trees["colormap"]) == {"2": [57, 125, 73, 255]}
    full = dict(parse_qsl(urlsplit(body["tiles"]["annual-land-cover"]).query))
    assert set(json.loads(full["colormap"])) == {"1", "2", "4", "5", "7", "8", "9", "10", "11"}
    assert body["search_id"] == "pc1.1.abc" and "tile_urls" not in body
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `uv run pytest backend/tests/test_catalogue.py backend/tests/test_land_cover_observation.py -q`
Expected: FAIL

- [ ] **Step 4: Implement the backend**

- Validation goes in a `model_validator(mode="after")` on `Layer`. It applies only when `tile_source == "mpc"`, and the error messages contain the strings tested above.
- In the endpoint, build `tiles` from `{layer.id: mosaic_tile_url(resolved.search_id, {int(i.value): i.colour for i in layer.legend.items}) for layer in mpc_layers}`, where `mpc_layers` is computed once in `create_app` next to `wants_observation`.

- [ ] **Step 5: Run the backend tests to make sure they pass**

Run: `uv run pytest backend -q`
Expected: all pass

- [ ] **Step 6: Implement the frontend**

- In `types.ts`, update the interface as above.
- In `MapView.tsx`, set `tiles: [data.tiles[layer.id]]` and `attribution: data.attribution`. Return `false`, so the layer waits as it does today, when `data.tiles[layer.id]` is missing.
- In `client.test.ts`, change the fixture to `tiles: {'annual-land-cover': 'https://planetarycomputer.microsoft.com/api/data/v1/mosaic/pc1.1.abc/tiles/WebMercatorQuad/{z}/{x}/{y}@1x.png?collection=io-lulc-annual-v02'}` and assert `Object.keys(observation.tiles)`.

- [ ] **Step 7: Write the e2e test** (`observations.spec.ts`)

```ts
test('two land layers from the observation share one request and draw from one mosaic', async ({ page }) => {
  // route /api/land-cover/observation*: count requests, fulfil {year: 2023, tiles: {'annual-land-cover': A, trees: B}, ...}
  //   with A and B on a fake host routed to a 1×1 PNG, recording each tile request's URL
  // open ?section=land-cover&layers=annual-land-cover:0.85,trees:0.85&year=2023
  await expect.poll(() => observationRequests).toBe(1)
  await expect.poll(() => tileHosts()).toEqual(new Set(['A', 'B']))   // tiles requested from both templates
  await expect(page.getByRole('region', { name: 'Active layers' }).getByText('Could not load')).toHaveCount(0)
})
```

`trees` won't exist in the real catalogue until Task 3, so this test adds it to the routed catalogue, as `observations.spec.ts` already does for its other cases.

- [ ] **Step 8: Run the frontend checks**

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npx playwright test e2e/observations.spec.ts`
Expected: tsc clean, all pass

- [ ] **Step 9: Commit**

```bash
git add backend/csa_portal/catalogue.py backend/csa_portal/main.py backend/csa_portal/land_cover_mpc.py backend/tests frontend/src frontend/e2e/observations.spec.ts
git commit -m "fix: annual land cover draws one MPC mosaic per layer instead of 11 item templates"
```

---

### Task 3: Replace the three local land rasters with MPC class views

**Files:**
- Modify: `backend/catalogue.json` (remove `forest`, `shrub-land`, `bare-land`; add five layers)
- Modify: `backend/scripts/prepare_rasters.py:33-38` (`RASTERS` keeps only `irrigated-rainfed`; fix the usage example on line 5)
- Test: `backend/tests/test_real_catalogue.py:178-200`, `frontend/e2e/url.spec.ts`

**Interfaces:**
- Consumes: the MPC layer validation from Task 2.
- Produces these catalogue layers. Each has `section_id: "land-cover"`, `kind: "raster"`, `status: "ready"`, `tile_source: "mpc"`, `max_zoom: 14`, `default_opacity: 0.85`, and the same `years` and `product` as `annual-land-cover`. Each legend is a single class:

  | id | title | value | colour | label |
  |---|---|---|---|---|
  | `trees` | Trees | 2 | `#397d49` | Trees |
  | `rangeland` | Rangeland | 11 | `#e3e2c3` | Rangeland |
  | `bare-ground` | Bare ground | 8 | `#a59b8f` | Bare ground |
  | `crops` | Crops | 5 | `#e49635` | Crops |
  | `built-area` | Built area | 7 | `#c4281b` | Built area |

  They go in the order shown, right after `annual-land-cover`. `irrigated-rainfed` stays as it is and is listed last.

- [ ] **Step 1: Write the failing real-catalogue tests**

```python
MPC_CLASS_VIEWS = {"trees": "2", "rangeland": "11", "bare-ground": "8", "crops": "5", "built-area": "7"}

def test_land_class_views_come_from_mpc_in_the_annual_maps_colours():
    by_id = {l.id: l for l in load_catalogue(BACKEND_DIR / "catalogue.json").layers}
    annual = {i.value: i.colour for i in by_id["annual-land-cover"].legend.items}
    for layer_id, value in MPC_CLASS_VIEWS.items():
        layer = by_id[layer_id]
        assert (layer.tile_source, layer.source, layer.years) == ("mpc", None, by_id["annual-land-cover"].years)
        assert [(i.value, i.colour) for i in layer.legend.items] == [(value, annual[value])]
    assert not {"forest", "shrub-land", "bare-land"} & set(by_id)
```

Set `LAND_COVER = {"irrigated-rainfed": {"2", "3"}}` so the two existing local-file tests cover only the layer that stays local.

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest backend/tests/test_real_catalogue.py -q`
Expected: FAIL (`KeyError: 'trees'`)

- [ ] **Step 3: Edit `catalogue.json` and `prepare_rasters.py`** per the table above

- [ ] **Step 4: Run the full backend suite and the recorded eval gate**

Run: `uv run pytest backend -q && uv run python backend/scripts/evaluate.py --gate backend/evaluations/baseline.json`
Expected: all pass, gate exit 0. Fix any test that uses `forest` as a *real* catalogue layer. `test_cog.py` uses its own synthetic catalogue and stays as it is.

- [ ] **Step 5: Write the e2e test for old links** (`url.spec.ts`)

```ts
test('a link naming a retired land layer drops it with a notice and keeps the rest', async ({ page }) => {
  await page.goto('/?section=land-cover&layers=forest:0.8,irrigated-rainfed:1')
  await expect(page.getByRole('status')).toContainText(/link/i)          // the existing dropped-values notice
  await expect(page.getByRole('region', { name: 'Active layers' }).getByText('Irrigated and rainfed cropland')).toBeVisible()
  await expect(page).not.toHaveURL(/forest/)
})
```

Match the notice locator to the one used by the existing `invalid values in a link are dropped` test at `url.spec.ts:38`.

- [ ] **Step 6: Run the whole frontend and e2e suites**

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npx playwright test`
Expected: all pass

- [ ] **Step 7: Live check against MPC** (manual; needs network)

Run `npm run dev`. Then confirm:

- `curl -s "http://127.0.0.1:9988/api/land-cover/observation?year=2023"` (the dev backend's default port, `dev_server.py:33`) returns 11 `item_ids` and 6 `tiles` keys.
- Fetching `tiles.trees` with `{z}/{x}/{y}` = `8/180/104` returns `200 image/png`.
- In the browser, the annual layer covers the whole country with no patchwork at z5–z9. Toggling Trees over it shows only green.

Record the results in the PR.

- [ ] **Step 8: Commit**

```bash
git add backend/catalogue.json backend/scripts/prepare_rasters.py backend/tests/test_real_catalogue.py frontend/e2e/url.spec.ts
git commit -m "feat: forest, shrub and bare-land layers become MPC class views; add crops and built area"
```

---

### Task 4: Record the decision and hand back the disk

**Files:**
- Create: `docs/adr/0003-land-classification-tiles-from-planetary-computer.md`
- Modify: `memory.md` (the Land Classification row in the sources table, run step 2, Open items)
- Modify: `CONTEXT.md` (glossary: **Class view**, a map layer showing one class of an observation; *Avoid*: forest layer, mask)

- [ ] **Step 1: Write ADR 0003**

The browser fetches land tiles from the MPC mosaic. The backend resolves only ids and serves only JSON. Statistics stay prepared, because MPC `/statistics` is unreliable and counts the item extent. Consequences: the portal depends on MPC's availability and terms, and an outage shows "Could not load" on these layers only. Irrigated/rainfed is the one land raster still local.

- [ ] **Step 2: Update `memory.md`**

- Under Open items, add: *the user may delete `backend/rasters/forest.tif`, `shrub-land.tif`, `bare-land.tif` and `tmpyt2t2_d9.tif`*.
- Also add: *follow-up: move `irrigated-rainfed` off this PC, and retire the static `land_cover.json` fallback and `prepare_land_cover.py`, which reads the deleted rasters*.

- [ ] **Step 3: Commit, push, open the PR against `feat/portal-data`**

```bash
git add docs/adr/0003-land-classification-tiles-from-planetary-computer.md memory.md CONTEXT.md
git commit -m "docs: land classification tiles come from Planetary Computer (ADR 0003)"
git push -u origin feat/mpc-land-mosaic
gh pr create --base feat/portal-data --title "Land classification served from Planetary Computer" --body "Closes #<issue>. ..."
```

---

## Out of scope (separate plans if wanted)

- **Irrigated/rainfed off this PC:** host its single COG in object storage, or find a published equivalent.
- **Retiring the static `land_cover.json` provider** (`sections.py:514-660`) and its tests. The annual statistics already replace it whenever `land_cover_annual.json` exists.
- **The notebook's swipe view** (first year against last) and its AOI-clipped thumbnails. The time slider and place highlight already cover browsing by year and place.
- **Live MPC statistics per drawn area.** Prepared statistics stay authoritative.

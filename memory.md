# CSA Portal — session memory

Written 2026-10-05, last updated 2026-10-15. A record of what was built in this session, the decisions behind it, and what is still open, so the next session can pick up without re-deriving it.

## What this is

A map-first Climate Smart Agriculture portal for Pakistan, for disaster management stakeholders. One large map, an icon rail of sections, a sliding panel with layers, figures and charts, and a full view where charts replace the map. Runs on localhost: FastAPI backend, React frontend.

## Running it

- **Start:** double-click `start-portal.cmd`, or `npm run dev` from the repo root.
- **Addresses:** frontend `http://127.0.0.1:9080`, backend on port 9988. The user chose these ports. Both `npm run dev` and the production scripts bind to `0.0.0.0`, so other machines on the same network can reach the portal at `http://<host-IP>:9080` (frontend proxies `/api` to the backend, so no CORS; Windows Firewall may need an inbound allow for Node/Python).
- **Local AI guide:** backend-only LM Studio integration at `http://127.0.0.1:1234`, model id `qwen/qwen3.8-27b` by default. Configure with `CSA_LM_STUDIO_*`. Overview and guided tour are deterministic; chat sends compact current-view context to Qwen, built through the facts module and sent through the language model seam (see *AI integration*). A grounded answer takes about 10 s on this machine.
- **Tests:** `npm test` (pytest, Vitest, Playwright). Browser tests use their own ports (8010 and 5183) and a fixture catalogue, so they can run while the portal is open.
- **On 2026-10-15:** 287 backend, 241 frontend logic and 75 browser tests passing. CI (`.github/workflows/ci.yml`: `quality` and `e2e` jobs) runs on every pull request; Playwright retries twice on CI only.

## State of the code

- **Branch:** `feat/portal-data` is GitHub's default branch for `imtiazNDMA/climatesmartagri` (public). Since 2026-10-15 work goes on a branch per ticket (`feat/<issue>-<slug>`, `fix/...`) with a pull request into `feat/portal-data`, merged with a merge commit once CI is green; `Closes #N` in the PR closes the issue. `main` and the shell branches beneath have never been pushed.
- **Kept out of git:** `data/geospatial/vectors/sajid(2oct)/` (about 700 MB) and `Aamir Ai  Project/` (2.4 GB: a separate crop-disease project with wheat, cotton and sugarcane data and a treatment guide), both in `.gitignore`.
- **Domain language and decisions:** `CONTEXT.md` (glossary: place, guidance vs warning, district risk, crop stage, fact, grounded, view action, advisory, crop health screening) and `docs/adr/` (0001 local model by default, 0002 advisories need officer approval).
- **Design documents:** spec and plan for the shell only, under `docs/superpowers/`. Everything after the shell was built from short designs agreed in chat.

## Sections

| Section | State | Source |
| --- | --- | --- |
| Land Classification | Live: the annual classification (2017–2023) and five class views (Trees, Rangeland, Bare ground, Crops, Built area), drawn by the browser from Microsoft Planetary Computer (ADR 0003); irrigated/rainfed cropland from a local raster; figures and charts per district from `backend/data/land_cover_annual.json` | MPC `io-lulc-annual-v02`; `data/geospatial/rasters/Irrigated&rainfed.tif` |
| Climate Smart Irrigation Practices | Live: 4 map layers, figures and charts per district | `Irr_Prac.shp`, irrigation sheet |
| Greenhouse-gas emissions | Live: charts, 1994–2025, national | `Pakistan_GHG_1994_2021_Excel_Data.xlsx` |
| Crop water balance | Live: charts, 2026–2047, national | `CRW(efficiency) 25sep.xlsx` |
| Food security projections | Live: charts, 2026–2047, national | `food security projection CSA 17 sep.xlsx` |
| Climate-smart crop calendar | Live: calendar chart per province | `apps/climate calender 28 sep 2026/script.js` |
| Weather forecast | Live since 2026-10-12: 47 layers from 8 models, fetched from PMD on demand | PMD early warning platform, `backend/forecast_layers.json` |
| Hazards | Live: 5 forecast-guidance products (frost, heat stress, heavy rain, strong wind, low visibility); frost uses a computed degree-hours layer | `backend/hazard_products.json`, `backend/hazard_models.json` |
| Exposure and vulnerability | Coming soon | No data yet |

## How data gets in

Three scripts turn source files into what the backend serves. Source files are never changed. Restart the portal after running any of them.

1. `uv run python backend/scripts/prepare_data.py` — boundaries, irrigation, emissions, water, food, crop calendar. Writes `backend/boundaries/` and `backend/data/`. About a minute.
2. `uv run python backend/scripts/prepare_rasters.py` — converts the irrigated/rainfed raster to a Cloud-Optimized GeoTIFF in `backend/rasters/` (not in git). Forest, shrub land and bare land are no longer converted: their layers are class views drawn from Microsoft Planetary Computer (ADR 0003).
3. `uv run python backend/scripts/prepare_land_cover.py` — measures each land-cover class per district from the converted rasters. Under a minute. Run after step 2.

## Architecture in one page

- **Layer catalogue** (`backend/catalogue.json`): every section and layer. The frontend builds the rail, panels, legends and time slider from it. Adding a layer is a catalogue entry plus data.
- **Layer kinds:** `geojson` (shapes coloured from the legend by a feature property), `raster` with a `source` file (served by TiTiler), `boundary`.
- **TiTiler** is mounted inside the backend at `/api/cog`. It only opens catalogue layers, never an arbitrary path, and colours tiles from the layer's legend.
- **Section data** (`backend/csa_portal/sections.py`): one provider per section returns figures, notes and chart specs. Charts are described by the backend and drawn generically by the frontend.
- **Chart kinds:** `line`, `stacked-area`, `bar` (ECharts, SVG renderer); custom components for `calendar`, `shares`, `diverging`, `counts`, `balance`, `outlook`, `explorer` and `grid`.
- **View state:** one Zustand store (open section, full view, active layers, place, year), mirrored to the URL: `section`, `view=charts`, `layers`, `hidden`, `place`, `year`.
- **Place fallback:** a section without figures at the selected level uses the nearest level above that has them (district → province → country).

## Weather forecast (added 2026-10-12)

- **Source:** PMD's "Cloud-based Early Warning Supporting System" at `https://115.186.56.181:12304`, Forecasting tab. The account is in `.env` at the repo root (git-ignored), read by `settings.py`. The user's original credentials file is still in the repo root and is git-ignored too.
- **How it works:** `backend/csa_portal/pmd.py` signs in and lists runs and files. `backend/csa_portal/forecast.py` picks, for each forecast time, the newest run that has a file, downloads that file on first request, cuts it to 55-85E, 18-42N and stores it under `backend/forecast/` (not in git) as an 8-bit file of colour positions. TiTiler serves it at `/api/forecast/cog`. Files older than 10 days are deleted.
- **Layer list:** `backend/forecast_layers.json`: each layer's PMD code, unit, colours, value range (per pressure level where needed) and which models and levels offer it. Changing a value range re-fetches, because the range is part of the stored file's name.
- **Frontend:** the section has `kind: "forecast"` in the catalogue. One forecast is on the map at a time, held in the view store as `forecast` and in the URL as `forecast=layer~model~level~time`. `ForecastPanel`, `ForecastSlider`, `useForecastTimes`, `forecast/choice.ts`.
- **PMD's certificate is self-signed.** The client does not switch verification off; it accepts only the certificate whose SHA-256 is in `CSA_PMD_CERT_SHA256`. If PMD renews its certificate the forecast stops with a certificate error until that value is updated.
- **PMD's server is slow and drops connections.** It reset partial-read requests, timed out a login when three browser sessions ran at once, and took over a minute to list times at its worst. Do not run several scripts against it at once.
- **PMD failures answer 424, not 502-504:** the frontend reads 502-504 as the portal's own backend being down.
- **What PMD had on 2026-10-12:** newest runs were 9 October, three days old; runs are often missing forecast hours. FENGWU had no data. PMD-ICON surface temperature files were a single row of cells (broken at the source). CIN, theta-se and integrated vapour transport exist only as August 2025 archive, so they are listed as having no current data.
- **Colour scales were tuned on 2026-10-12 against one real file for each of the 203 model-and-level choices.** A layer can have `stops` (a value per colour, for skewed quantities: all precipitation, CAPE, visibility, precipitation anomaly percent), `ranges` per pressure level, `model_ranges` and `model_factors` per model, and `ignore_above`. The tuning files were from a dry October week, so ranges were kept wide enough for other seasons rather than fitted to that week.
- **Models disagree on units for the same layer.** ECMWF specific humidity is kg/kg where the others are g/kg (factor 1000). PMD-WRF low cloud is a fraction where the others are percent (factor 100). ECMWF thickness is 316-490 where FENGQING and PANGU give 553-585 (own range; what ECMWF's figure measures is unknown). PMD-WRF wind files mark missing cells with 9999 in each component (`ignore_above`).
- **Choices left out because PMD had no usable file:** PMD-ICON wind, temperature, max and min temperature, dew point, relative humidity and max 10 m wind (single-row files), PMD-ICON geopotential height and PMD-WRF total cloud (runs listed, no files), FENGQING and PANGU specific humidity at 200 hPa (all zeros at the stored precision). Put them back in `forecast_layers.json` if PMD fixes them.
- **Playback blends one time into the next** (`frontend/src/map/forecastFrames.ts`): each time is its own raster layer, added invisibly, shown only once its tiles have loaded, cross-faded over 450 ms with the one before. The time after the one on screen is loaded out of sight in advance, and playing waits for a time still loading. Removing the layer and adding a new one per time is what made it jerk.
- **Caching, by layer:** forecast tile addresses name the model run, so they never change and are sent `immutable` for a week; the browser replays an animation without asking the server. A list of times is used for 10 minutes, then still handed out at once while a fresh one is fetched behind it, and is saved under `backend/forecast/_listings/` so a restart or a PMD outage does not lose it. A file already on disk is served by its run without asking PMD anything. A failed fetch is remembered for a minute (ten for an unusable file) so the tiles of one view do not each retry it. Land-cover tiles are kept by the browser for an hour. Failures are always `no-store`.
- **Not built:** wind arrows, geopotential contour lines, the City/Position text bulletins, a click-for-value popup on forecast layers.

## The card deck (2026-10-12)

- **Every section shows its layers as cards** (`.deck-*` in `styles.css`): a small chart in the layer's own colours (`components/fieldArt.ts`, a picture of the colours, not of the data), the name, and what the colours stand for. The whole card is the switch; several can be on, each with a tick. The user chose this from three prototypes (a refined list, the card deck, a dark console) and asked for it on every section.
- **The forecast panel** (`ForecastPanel.tsx`) adds a banner for what is on the map (hour large, scale with tick values, kind, period, model and level buttons) and tabs for the six kinds of layer. Layers that are one quantity cut different ways are merged into one card with choosers (`forecast/entries.ts`): 16 precipitation layers are one "Precipitation" card.
- **Motion** (anime.js 4 in `components/deckMotion.ts`, the rest CSS): a picked card's picture flies up into the banner; the scale draws in from its low end; the hour rolls from the old time to the new; a pill slides between choices in the tracks and tabs; the banner's contour rings drift slowly (the only motion nobody asked for); cards arrive in a stagger; the tick pops and draws. All of it is off under reduced motion. The user asked for "all relevant animations"; hover tilts, parallax and looping attention effects were deliberately left out.

## Charts, changes on 2026-10-12

- **Nothing in a chart is faded for emphasis.** The user asked for every bar and label at full strength; the rows a headline is about are bold only. The crop calendar's faded traditional dates were left, since the fade is how it tells them from the adjusted ones.
- **Enlarged charts use larger text and thicker bars**; the small ones in the panel are unchanged.
- **The groundwater and surface water chart singles out no province** unless the user has selected a place. The user rejected my rule (highest shares among provinces with at least 2% of equipped land) once they saw it left Gilgit Baltistan's 100% unmarked. The same 2% floor still picks the land-cover headline ("farm mostly on rain"); the user has not said whether to change it.
- **The emissions chart on official measurements was removed** at the user's request. Nothing now tells the six official years from the filled-in ones.
- **Food security has one outlook chart** (`OutlookChart.tsx`, kind `outlook`) in place of the two line charts, drawn after the user's `CSA_food_security_storytelling.png`: need, supply with CSA and supply with traditional farming, with the two spaces between filled and measured. Pointing reads a year out, a click or the arrow keys set the portal's year, and the bands and every-year figures can be switched off.
- **Crop water balance has two new charts** (`WaterCharts.tsx`, kinds `explorer` and `grid`) in place of the break-even and need-versus-supply lines, which the user found redundant. The explorer draws water available against water needed at an efficiency set by a slider; the grid shows every efficiency against every year with the break-even line through it. They share one efficiency (`uiState.efficiency`). Both rest on need times efficiency being constant, which holds exactly at the source's 35%, 50% and 70%; values between are calculated, a note under each chart says so, and the backend leaves both charts out if the source's levels ever stop agreeing. The user was told Dr Aamir should confirm the rule across the range.
- **Food security's units are unknown.** The workbook states none. Million tonnes is my inference (364 kg per person per year); its "food" totals include cash and other crops; and two versions of the climate smart series exist (the `csa` sheet, which the portal reads, starts at 82.855; another sheet's "With best practices" starts at 86.155). The user was told and has not yet decided on relabelling.
- **A section's charts now stay on screen while another year loads** (`useSectionData`). Before, every year step threw the charts away and drew them afresh.

## Hazards guidance (added 2026-10-14)

- **The Hazards section is live** with five forecast-guidance products: frost risk, heat stress, heavy rainfall, strong wind and lodging, and fog/low visibility. They are guidance derived from PMD forecast fields, not official warnings; the panel says so on every open.
- **`backend/hazard_products.json`** holds each product's id, PMD layer, unit, direction and three severity bands with provisional thresholds, plus a `threshold_version` and disclaimer. `backend/csa_portal/hazards.py` validates the file (ordered bands, known direction) and serves `GET /api/hazards/products`; `CSA_HAZARD_PRODUCTS` overrides the path. The section's `kind` is `hazards` in the catalogue, which also switches on the forecast service in `main.py`.
- **The panel drives the ordinary forecast machinery**: picking a product calls `chooseLayer` and sets the view store's `forecast`, so the map pipeline, `ForecastSlider` and the URL (`forecast=layer~model~level~time`) work unchanged. It opens on the first product that has data when nothing is on the map. Model choice and valid time come from the existing forecast controls.
- **Thresholds are interpretive, not calibrated.** The map shows the raw PMD field's own colour ramp, not the band colours; the bands and thresholds are a screening aid in the panel. They live in the JSON so they can be revised without touching code.

## Forecast-derived hazard models (added 2026-10-14)

- **Frost risk now uses a real derived model, not instantaneous temperature-min.** `frost-degree-hours` accumulates how far below 0 °C each cell has been over a rolling 24-hour window (degree-hours: 1 °C below for 6 hours scores 6). Deeper and longer cold means more damage; the old instantaneous field missed that entirely.
- **Colour positions are lossy; models need real values.** `ForecastService.file()` stores colour positions (uint8 1–255) for tiles — good enough to draw, not to compute from (0.27 °C per step). Any download now also writes a float32 `_values.tif` beside the colour file (`read_physical` / `write_positions` / `write_values` in `forecast.py`). A colour file can be rebuilt from values; values cannot be rebuilt from colours, so they are re-fetched once if missing. Both are written on the same download.
- **`backend/hazard_models.json`** lists the derived models; `backend/csa_portal/hazard_models.py` validates them (`DerivedSpec`) and serves them (`DerivedService`). Models are not in `ForecastRegistry` — `add_forecast_routes` delegates `times` / path / colourmap for derived ids to the service, and `main.py` merges `derived.describe()` into the catalogue's forecast body under a `hazard-models` group. The frost product in `hazard_products.json` points at `frost-degree-hours` with ascending bands 3 / 12 / 24 °C·h.
- **A derived time appears only when its input window is full enough.** `times()` keeps a slot only when the run offers at least `min_points` (4) input valids inside the last `window_hours` (24). Computing reads each window time's real-value file, stacks them, runs the pure function in `backend/csa_portal/models/frost.py`, and caches the result under `_derived/`. First view of a window costs up to 8 downloads; the frontend's `/api/forecast/cog/info` prefetch warms it.
- **Adding another model is JSON plus a pure function.** Heat degree-hours, heavy-rain rolling totals and wind lodging follow the same pattern: a compute function registered in `models/__init__.py`'s `COMPUTES`, a spec in `hazard_models.json`, and a band set in `hazard_products.json`.

## Changes on 2026-10-15

- **Land-cover tiles no longer 404 outside Pakistan.** Each ready raster layer in `/api/catalogue` carries `bounds` (its extent in degrees, read from the file and cached by modified time), and the map passes them to MapLibre so it asks for no tiles beyond. The 404s were TiTiler correctly answering "outside bounds" for every tile on screen.
- **ECharts 6:** `grid.containLabel` replaced by `outerBoundsMode: 'same', outerBoundsContain: 'axisLabel'`.
- **Renamed at the user's request:** sections "Land Classification" and "Climate Smart Irrigation Practices"; the land-cover class "Bare land" is "Others" in charts and figures (the map layer and its legend still say "Bare land"; the user was asked and has not said). The portal title is 40px.
- **The land-cover shares chart shows no percentages:** headline "How <place>'s land is classified", no values beside the bars, no table.
- **Dark mode reads at 4.5:1 or better everywhere.** ECharts takes a dark palette (`chartOption(spec, year, large, dark)`, theme from `state/useDarkTheme.ts`); dark-only CSS overrides at the end of `styles.css` cover the water balance, explorer, calendar, irrigation counts and diverging titles. Light mode is unchanged. A contrast audit (every visible HTML and SVG text against its real background, panel and full view) found these; the tests did not.
- **Full-view side titles no longer collide** on cards narrower than 520px (two to a row at about 1600px): container queries shrink names and titles, and the irrigation chart's left title may reach over the name column.
- **CI flake fixed:** the map-click test clicked while the camera was still moving to the place it had just selected. The map now sets `data-camera-on` to the place id when a move ends; tests wait on it instead of on fixed timeouts.

## AI integration (planned and started 2026-10-15)

- **Plan:** PRD issue #1 with 20 sub-issues (#2–#21), linked as GitHub sub-issues with native blocking dependencies, labelled `ai` plus a triage label. Tracks: foundations (#2–#5), assistant v2 (#6–#10), advisories (#11–#14), crop health (#15–#18), research (#19–#21).
- **User decisions:** local model by default with a hosted model optional per deployment (ADR 0001); AI-drafted advisories are approved by an officer before they leave the portal (ADR 0002); all four tracks in scope.
- **Done:** #3 facts (`backend/csa_portal/facts.py`: `section`, `district_risk`, `find_place`, `portal`; every value a chart draws is a fact with a source) and #2 language model seam (`backend/csa_portal/language_model.py`: `chat`, `complete` with tools or a pydantic output shape, `stream`; adapters `LmStudioModel` and `ScriptedModel`). Merged as PRs #22 and #23.
- **Qwen3 on LM Studio files a schema-bound reply as `reasoning_content` and leaves `content` empty.** The adapter reads it from there. Found only by testing against the real server; the fake server could not show it.
- **Next on the critical path:** #4 evaluation suite (baseline score of the current assistant before #7 changes it), then #7 tools over facts. #5 and #6 are also unblocked.
- **The separate AI project** (`Aamir Ai  Project/`) covers wheat, cotton and sugarcane with a treatment guide; #15 and #17 plan to bring it in. The portal's own classifier (`improved-002`) is Rice and Maize only and untested on Pakistan field images.

## Decisions the user made

- Audience is general disaster management stakeholders; everything must be interactive.
- Localhost, FastAPI and React. Ports 9988 and 9080.
- Layout: fixed icon rail, sliding panel, bottom time slider. Layers persist across sections.
- `Join_Irrigated_Full.shp` is the main district map, including the Kashmir region: 167 districts in 8 provinces and territories.
- The Kashmir region displays as "Jammu and Kashmir". That name came from edits made in the repo outside this session, and was kept.
- Charts open in a full view that replaces the map.
- Charts are written for storytelling in plain language: a headline that states the finding, labels on the lines. The line of explanation under each headline was removed at the user's request on 2026-10-07, in every section.
- Rasters are served with TiTiler.
- Notes under the land cover figures were removed at the user's request, both of them.
- For builds after the shell: a short design in chat, then build. No separate spec and plan documents.

## Decisions I made that the user has not confirmed

- **Irrigation practice codes:** SP = sprinkler, AWD = alternate wetting and drying, FI = flood irrigation.
- **District name matching:** 20 spreadsheet names mapped to map names by spelling or former name (`DISTRICT_SPELLINGS` in `prepare_data.py`), for example Attok → Attock, Nawabshah → Shaheed Benazir Abad, Bolan → Kachhi.
- **Seven spreadsheet rows are not placed on the map** and count in totals only: Karachi, Dir, Chitral, Kohistan, Gahkuch, "Sheikhupura (Nankana)", "Mirpurkhas and Umerkot".
- **Population is labelled "million".** Water and food amounts show no unit because the sources give none.
- **Emissions uses the sheet in the combined workbook** (`Complete GHG and Irrigation data 30 Sep.xls`), which runs to 2025, since 2026-10-07 at the user's request. Its nitrous oxide and totals differ from the standalone workbook from 2016 on; the standalone one is read only for the source's name.
- **Land cover is measured on a one-in-64 sample** of the 10 m rasters' cells.
- **Crop calendar:** "Oct/Nov" draws as the wider range; "early" and "mid" draw as half a month; "sow earlier" means a sowing window now ends sooner.
- **The capital shows as "Federal Capital",** as the district map names it.

## Things learned the hard way

- **The source rasters are not in git.** `data/geospatial/rasters/` and `data/archives/` (about 7 GB, nine files over GitHub's 100 MB limit) were in the first commit and made every push impossible. On 2026-10-12, at the user's choice, all four branches were rewritten without them and the folders git-ignored; the files are still on disk. The history from before is kept locally under `backup/before-slimming/*`. Do the same in a separate clone if it is ever needed again: `filter-branch` in the working repo would delete the files from disk.
- **`data/geospatial/vectors/sajid(2oct)/` is untracked** and holds three files over 100 MB, including `Join_Irrigated_Full.shp`, the district map's source. It cannot be pushed as it is.

- **Never stop processes by port.** Early on I killed everything listening on ports 8000 and 5173 and took down the user's unrelated "Seismic Intelligence Platform". Since then I stop only processes whose command line is inside this project (`stop.ps1` in the session scratchpad did this; it is not in the repo).
- **`PROJ_LIB` on this machine points at PostgreSQL/PostGIS's older projection database** and breaks rasterio. `backend/csa_portal/geoenv.py` switches to the bundled copy; it must run before rasterio is imported.
- **Raster overviews must be built by sampling ("nearest").** Voting overviews that skip empty cells painted Punjab and Sindh as solid forest from far out.
- **A raster conversion can silently lose its zoomed-out copies** if the temporary file passes 4 GB. The script now compresses the temporary file and rejects a result whose overviews are empty.
- **MapLibre 6 under Vite needs its worker URL set explicitly** (`setWorkerUrl` with a `?worker&url` import), and has no default export.
- **The backend caches raster files and section data.** Restart it after re-running a preparation script. Since 2026-10-07 `npm run dev` runs `backend/scripts/dev_server.py`, which restarts the backend by itself when its code, `catalogue.json`, prepared data or boundaries change. Do not use uvicorn's `--reload` here: on Windows it stops the old server with a console Ctrl+C, which also kills the frontend and launcher in the same window.
- **Tests do not judge whether a chart reads well.** Looking at screenshots of the real portal caught overlapping labels, clipped names and the forest overstatement.

## Open items

- **Delete `backend\rasters\tmpyt2t2_d9.tif`** (5.6 GB), left from a conversion I stopped. A safety check blocked my clean-up, so it is the user's to remove.
- **The user may delete `backend\rasters\forest.tif`, `shrub-land.tif` and `bare-land.tif`**: since #59 nothing serves them (their layers are MPC class views). `prepare_land_cover.py` still reads them, and it is retired in #62.
- **Irrigated/rainfed is the last land raster on this PC** (#61): it needs a hosting decision.
- **Hazards guidance** is live but its thresholds are provisional (`provisional-2026-10`); they have not been reviewed against impact data or PMD's own warning thresholds. **Exposure and vulnerability** still have no data. The district map carries a population figure per district (about 313 million in total) that would suit exposure.
- **The background map draws its own borders** and Kashmir labels beneath the project's boundaries. The style is a setting (`CSA_BASEMAP_STYLE_URL`).
- **The tehsil practice layer uses a different boundary set** from the district map, so edges do not line up exactly, and it has no tehsils in Jammu and Kashmir.
- **Nothing on the page says why land cover shares exceed or fall short of 100%** now that the notes are gone.
- **Units for water and food** are still unknown.
- **Only the shell had an independent code review.** Everything on `feat/portal-data` has tests but no second reviewer.
- **Deferred from the shell review:** search says "No places match" when boundaries are missing; lenient number parsing in the URL; the URL is rewritten on every change; some validation errors use a different shape; "Check again" gives no feedback when the backend is still down.
- **`main` has never been pushed.** Everything merges into `feat/portal-data`, the default branch; the user has not said whether it should ever reach `main`.
- **This repo is public, and this file names the PMD server's address and port** (*Weather forecast*). The user was told on 2026-10-15 and has not decided whether to remove it.
- **AI decisions waiting on the user:** #21 which documents the assistant may answer from, #15 which agronomist reviews management guidance.
- **Deferred:** officer sign-in (#12), advisory approval workflow, export and sharing. Advisories may remain clearly marked internal drafts, with no external distribution. Revisit ADR 0002 only if publishing or sharing enters scope.
- **The `/api/sections/{id}/data` route still has its own copy of the place fallback**; moving it onto the facts module is a small follow-up.
- **Crop disease model (#65, started 2026-10-27).** Plan: #66 data → #67 PyTorch + MLflow baselines → #68 autoresearch harness → #69 run → #70 calibrate/package → #71 portal. User decisions: PyTorch (not TF; TF has no Windows GPU), one 5-crop model replaces `improved-002` only if it wins on rice/maize, macro F1 on val selects and the locked test is scored once, code in `ml/crop-disease/` and images outside git (`CSA_CROP_DATA_DIR`). #66 (PR #72): 57% of the original test images were copies of training images; the clean manifest has 11,453 unique images, 37 classes. Waiting on Dr. Aamir: the bollworm merge, armyworm vs fall armyworm, and pink bollworm (dropped as too small, but a major pest). #17 is superseded by #65 pending the user's OK to close it.
- **GitHub labels:** the triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`) and `ai` exist on `imtiazNDMA/climatesmartagri`.

## AI platform core (designed 2026-10-16)

- **Goal:** turn the assistant into an agentic AI platform with proper evaluation and a monitoring dashboard; the user also wants it as a CV piece.
- **Spec:** `docs/superpowers/specs/2026-10-16-ai-platform-core-design.md`, PR #26 (branch `docs/ai-platform-core-spec`). The user approved a written spec for this one because it spans about 7 PRs; short chat designs still apply to smaller builds.
- **Issues:** PRD #27 (sub-issue of #1) with steps #28 runtime, #29 tracing and store, #30 evaluation v2, #31 local judge, #32 ops API, #33 `/ops` dashboard, each blocked by the one before; #28 is blocked by #7. #5 is covered by #29 and #30.
- **User decisions:** own span schema in SQLite with OpenTelemetry GenAI names and optional OTLP export (not Langfuse/Phoenix or LangGraph); thin in-house agent runtime, workflows as plain Python; LLM judge is a second **local** model, trusted only once calibrated against human labels (20+ labels, kappa 0.6+); dashboard at `/ops` in the portal behind `CSA_OPS_TOKEN`.
- **Next:** step 0, finish #7 on `feat/7-assistant-fact-tools` and run the live evaluation for the before-platform number, then the implementation plan for #28.

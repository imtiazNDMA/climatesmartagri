# Climate Smart Agriculture Portal

A map-first portal for Pakistan's climate smart agriculture data, built for disaster management stakeholders.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Node 20 or later.

On Windows, double-click `start-portal.cmd`. It installs anything missing, starts the backend and frontend, and opens the portal. If the portal is already running it just opens it. Close the window to stop the portal.

Or by hand:

    uv sync
    npm install
    npm --prefix frontend install
    npm run dev

The portal opens in your browser. The backend runs on port 9988 and the frontend on 9080. The background map needs internet access.

## Test it

    npm test

This runs the backend tests (pytest), the frontend logic tests (Vitest) and the browser tests (Playwright). The first time, install the test browser with `npm --prefix frontend exec playwright install chromium`.

## Layout

- `backend/` — FastAPI app. `catalogue.json` describes every section and layer; the interface is built from it.
- `backend/boundaries/` and `backend/data/` — boundaries and section data, produced from the files in `data/` by `uv run python backend/scripts/prepare_data.py`. Re-run it after changing a source spreadsheet or map file, then restart the portal.
- `frontend/` — React app.
- `data/` — source datasets.
- `docs/superpowers/specs/` — design documents.

## Land-cover rasters

The four land-cover rasters in `data/geospatial/rasters` are served by [TiTiler](https://developmentseed.org/titiler/), which runs inside the backend. They must first be converted to Cloud-Optimized GeoTIFFs:

    uv run python backend/scripts/prepare_rasters.py

This writes `backend/rasters/` (not kept in git; about 1 GB in total) and takes a long time for the 10 m files. A layer shows as "Data not loaded yet" until its file is converted. Restart the portal after converting.

## Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `CSA_CATALOGUE_PATH` | `backend/catalogue.json` | Catalogue file |
| `CSA_BOUNDARIES_DIR` | `backend/boundaries` | Boundary GeoJSON folder |
| `CSA_BASEMAP_STYLE_URL` | OpenFreeMap Positron | Background map style |
| `CSA_DATA_DIR` | `backend/data` | Prepared section data |
| `CSA_RASTERS_DIR` | `backend/rasters` | Converted land-cover rasters |

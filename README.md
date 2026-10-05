# Climate Smart Agriculture Portal

A map-first portal for Pakistan's climate smart agriculture data, built for disaster management stakeholders.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Node 20 or later.

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

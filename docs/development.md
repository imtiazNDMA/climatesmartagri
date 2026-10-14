# Development guide

## Prerequisites

- Python 3.13
- uv
- Node.js 22.12 or later

## Setup

```sh
uv sync
npm ci
npm --prefix frontend ci
```

Use `.env.example` as the list of supported local settings. Keep credentials in an untracked `.env` file.

## Commands

| Command | Purpose |
| --- | --- |
| `npm run dev` | Run the API and Vite development server |
| `npm run check` | Lint, unit-test, and build the application |
| `npm test` | Run backend, frontend, and browser tests |
| `npm run build` | Produce the frontend production bundle |
| `npm run start:api` | Run the production API process locally |
| `npm run start:web` | Preview the built frontend locally |

## Data workflow

Raw source data belongs under `data/`. Generated runtime data belongs under `backend/data/` and `backend/boundaries/`. Generated research plots and notebooks belong under `artifacts/analysis/` and must not be imported by runtime code.

Run `uv run python backend/scripts/prepare_data.py` after changing supported source files. Land-cover COGs are built separately with `backend/scripts/prepare_rasters.py` and remain untracked because of their size.

## Pull requests

Before opening a pull request, run `npm run check`. Run `npm test` when the change affects browser behavior. Do not commit credentials, caches, local virtual environments, large source rasters, or PMD forecast downloads.

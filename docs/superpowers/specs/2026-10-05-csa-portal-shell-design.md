# Climate Smart Agriculture Portal — Shell Design

Date: 2026-10-05
Status: awaiting review
Sub-project: 1 of 4 (portal shell)

## Purpose

A map-first Climate Smart Agriculture (CSA) portal for Pakistan, used by general disaster management stakeholders as a decision-support tool. Each layer should help answer "where is the risk, and how bad".

The portal is a giant map with an icon rail of section buttons. Everything is interactive: layers switch on and off, places can be selected, charts follow the selection, and a time slider moves the map and charts through the years. There are no static chart images.

## Decisions already made

| Topic | Decision |
| --- | --- |
| Audience | General disaster management stakeholders |
| Hosting | Localhost, internet access available |
| Stack | FastAPI backend, React frontend |
| Layout | Fixed icon rail, sliding section panel, bottom time slider |
| Layer behaviour | Layers persist across sections, managed in an active layers list |
| Place selection | Provinces and districts; draw-an-area is a later addition |
| Data serving | File-based tiles served by FastAPI, no database server |
| Hazard and exposure | Designed into the layout now, marked "coming soon" until data is sourced |

## The whole project in four sub-projects

1. **Portal shell** (this spec) — layout, shared controls, layer catalogue, boundaries.
2. **Data preparation** — convert the large rasters and vector files into tile-friendly formats and pre-compute district statistics.
3. **Sections 1–6** — land cover, irrigation, emissions, water balance, food security, climate calendar, wired in one at a time.
4. **Hazard and exposure** — source public data, get it approved, then build sections 7 and 8.

Each sub-project gets its own spec, plan and build.

## Scope of the shell

### Delivered

- A portal running on localhost with the full layout and all shared behaviour.
- A basemap, province boundaries and district boundaries.
- All eight sections registered in the catalogue and reachable from the rail.
- Place selection, search, breadcrumb, active layers list, legend, time slider and shareable address-bar state, all working against the catalogue.
- Empty states for sections that have no data yet.

### Not delivered

- Land-cover and irrigation map layers (sub-project 2).
- Figures and charts for any section (sub-project 3). The shell renders the Figures and Charts blocks with their empty states only.
- Hazard and exposure data (sub-project 4).
- Logins, user uploads, draw-an-area analysis.
- Offline basemap.

## Architecture

```
csa/
├── backend/     FastAPI app
├── frontend/    React + TypeScript app (Vite)
├── data/        existing source data, unchanged
└── apps/        existing climate calendar, folded in during sub-project 3
```

- **Backend:** Python, FastAPI, managed with the repo's existing `uv` project. It owns the layer catalogue, the places list, boundary data, tile endpoints and section data endpoints.
- **Frontend:** React with TypeScript, built with Vite. MapLibre GL JS draws the map. Zustand holds the shared view state.
- **Basemap:** an OpenFreeMap vector style loaded over the internet. The style URL is a backend setting so it can be changed without touching code.
- **Boundaries:** a public administrative boundary dataset for Pakistan at province and district level (candidate: the OCHA common operational dataset published on the Humanitarian Data Exchange). The dataset's licence and its depiction of borders must be confirmed by the project owner before it is committed. In the shell, boundaries are served as simplified GeoJSON; sub-project 2 may move them to vector tiles without changing the catalogue entry's identity.
- **Starting the portal:** one command, `npm run dev` at the repo root, starts the backend and the frontend together and opens the browser.

## The layer catalogue

The backend holds one catalogue, a single file under `backend/`, that describes every section and layer. The frontend reads it at start-up and builds the rail, panels, legends and time slider from it. Adding a layer later means adding a catalogue entry and its data, with no interface changes.

### Section entry

| Field | Meaning |
| --- | --- |
| `id` | Stable identifier, used in the address bar |
| `title` | Name shown in the rail tooltip and panel heading |
| `icon` | Icon name |
| `order` | Position in the rail |
| `status` | `ready`, `no-data` or `coming-soon` |
| `place_levels` | Which levels have figures: any of `national`, `province`, `district` |
| `years` | First and last year of data, or absent if the section has no yearly data |

### Layer entry

| Field | Meaning |
| --- | --- |
| `id` | Stable identifier, used in the address bar |
| `section_id` | The section whose panel lists this layer |
| `title` | Name shown in the panel and the active layers list |
| `kind` | `raster`, `vector` or `boundary` |
| `status` | `ready` or `no-data` |
| `legend` | List of colour and label pairs, or a colour ramp with minimum and maximum |
| `years` | First and last year, or absent |
| `default_opacity` | Starting transparency |

### Sections registered in the shell

| Order | `id` | Title | Status in shell |
| --- | --- | --- | --- |
| 1 | `land-cover` | Land cover | `no-data` |
| 2 | `irrigation` | Irrigation practices | `no-data` |
| 3 | `emissions` | Greenhouse-gas emissions | `no-data` |
| 4 | `water-balance` | Crop water balance | `no-data` |
| 5 | `food-security` | Food security projections | `no-data` |
| 6 | `climate-calendar` | Climate calendar | `no-data` |
| 7 | `hazards` | Hazards | `coming-soon` |
| 8 | `exposure` | Exposure and vulnerability | `coming-soon` |

The boundary layers (`provinces`, `districts`) are always on and are not listed in any section panel or in the active layers list.

## Backend API

All routes are under `/api`.

| Route | Returns |
| --- | --- |
| `GET /api/health` | Backend status and, per layer, whether its data is loaded |
| `GET /api/catalogue` | All sections and layers, plus the basemap style URL |
| `GET /api/places` | Provinces and districts: `id`, `name`, `level`, `parent_id`, bounding box |
| `GET /api/places/boundaries?level=province\|district` | Simplified boundary GeoJSON; each feature carries the place `id` |
| `GET /api/tiles/{layer_id}/{z}/{x}/{y}` | A map tile for a layer |
| `GET /api/sections/{section_id}/data?place={id}&year={year}` | Headline figures and chart series for a section |

Behaviour fixed by this spec:

- Place identifiers are the boundary dataset's own administrative codes. `PK` identifies the whole country.
- `place` defaults to `PK`. `year` defaults to the section's latest year.
- Unknown `layer_id`, `section_id` or `place` returns 404 with a message naming what was not found.
- A `year` outside the section's range returns 422.
- A layer or section whose status is `no-data` or `coming-soon` returns 404 with a `reason` of `no-data` or `coming-soon`, so the frontend can tell this apart from a mistake.
- In the shell, every tile route and every section data route returns that `no-data` or `coming-soon` response. Sub-projects 2 and 3 replace them.
- A section asked for a level it has no figures for returns its national figures with `level_used: "national"`, so the frontend can say so.

## The screen

```
┌──┬────────────┬──────────────────────────────────────┐
│▣ │ Land cover │ [Search place…]      Pakistan › Sindh │
│──│ ────────── │                                       │
│🗺│ ☑ Forest   │                          ┌──────────┐ │
│💧│ ☐ Shrub    │                          │ Active   │ │
│🌫│ ☐ Bare     │            MAP           │ ▪ Forest │ │
│🌾│ ☑ Irrigated│                          │ ▪ Irrig. │ │
│🍞│ ────────── │                          └──────────┘ │
│📅│ Figures    │                                 [+][−]│
│⚠│ for Sindh  │ ┌─────────┐                           │
│👥│ ────────── │ │ Legend  │                           │
│  │ Charts     │ └─────────┘                           │
│──│            ├───────────────────────────────────────┤
│ⓘ│            │   ◄  1994 ─────●────────── 2021  ►  ▶ │
└──┴────────────┴───────────────────────────────────────┘
```

### Components

Each is one unit with one job. All read and write the shared view state; none talk to each other directly.

| Component | Job |
| --- | --- |
| Icon rail | Eight section buttons in catalogue order, plus an About button. Highlights the open section. Shows a dot on sections with active layers and a marker on `coming-soon` sections. Section names appear on hover and are available to screen readers. |
| Section panel | Slides out beside the rail. Three blocks in fixed order: Layers, Figures, Charts. Closes when the open section's button is clicked again. Its width can be dragged. |
| Map | Draws the basemap, boundaries and active layers. Handles hover, click and zoom. |
| Place search | Finds a province or district by name and selects it. |
| Breadcrumb | Shows the selection, such as Pakistan › Sindh › Thatta. Clicking a part steps back up to it. |
| Active layers list | Lists every active layer from any section, each with a transparency slider, a hide toggle and a remove button. Drag to reorder; the top of the list draws on top. |
| Legend | One key per active layer, in the same order as the active layers list. |
| Time slider | Year slider with step and play controls. |
| About dialog | Data sources and credits. |

### Behaviour

- **Hover** on the map highlights the district under the pointer and shows its name.
- **Click** with nothing selected selects the province under the pointer. Click inside the selected province selects the district under the pointer. Click in a different province selects that province. The selected area is outlined and the map zooms to its bounding box.
- **Switching sections** changes the panel only. Active layers stay on the map until removed.
- **Time slider visibility:** shown when the open section or any active layer has `years`. Its range is the widest span across those. A layer or section with no data for the chosen year uses its nearest available year, and the legend entry shows which year is displayed.
- **Charts and figures** always follow the open section, never the stack of active layers.
- **National-only sections:** when a province or district is selected and the section has no figures at that level, the Figures block shows "National figures only" above the national numbers.

### Address-bar state

The view is mirrored to the URL query string so it can be bookmarked or reloaded:

| Parameter | Example | Meaning |
| --- | --- | --- |
| `section` | `land-cover` | Open section; absent means the panel is closed |
| `layers` | `forest:0.8,irrigated:1` | Active layers top to bottom, each with its opacity |
| `hidden` | `forest` | Active layers currently hidden |
| `place` | `PK8` (illustrative) | Selected place identifier; absent means Pakistan |
| `year` | `2015` | Selected year; absent means the latest |

Unknown values are dropped, a notice lists what was dropped, and the rest of the view loads.

### Smaller screens

Designed for desktop and large displays. Below 900 pixels wide, the section panel covers the map as a full-height sheet with a close button, and the rail stays visible.

## Data flow

1. **Start-up:** the frontend requests the catalogue and the places list, then the two boundary files. It reads the address bar and applies what is valid.
2. **Layer switched on:** the layer is added to the top of the active list. The map requests its tiles as the view changes.
3. **Place or year changed, or section opened:** the frontend requests the open section's data for the current place and year and redraws the Figures and Charts blocks.

### Shared view state

One store holds four things: the open section, the active layers (order, opacity, hidden), the selected place and the selected year. It exposes actions for each change, such as open section, toggle layer, set opacity, reorder layers, select place, step up, set year. The address-bar mirror is the only other writer.

## Failure handling

| Situation | What the user sees |
| --- | --- |
| Backend unreachable at start-up | A full-screen message that the portal cannot reach its data service, the command to start it, and a retry button |
| Backend lost while in use | A banner at the top; the current view stays on screen; controls that need the backend show the same notice |
| A layer's tiles fail | A warning on that layer in the active layers list with a retry button; other layers keep working |
| Section status `no-data` | "Data not loaded yet" in the panel's Layers, Figures and Charts blocks |
| Section status `coming-soon` | "Coming soon" with one line on what the section will show |
| No figures at the selected level | "National figures only" and the national numbers |
| Basemap unreachable | Boundaries and data layers on a plain background, with a small notice |
| Invalid address-bar values | Dropped, with a notice naming them |

## Testing

Tests are written before the code they cover.

- **Backend (pytest):** every route in the API table, covering the success response, unknown identifiers, a year out of range, `no-data` and `coming-soon` responses, and the fallback to national figures. A check that the catalogue file is valid: unique identifiers, every layer's `section_id` exists, statuses are from the allowed set.
- **Frontend logic (Vitest):** the shared view state, covering toggling, reordering, hiding and removing layers, selecting a province then a district, stepping back up, and year changes. The address-bar mirror, covering round-tripping a full view and dropping invalid values. The time slider's visibility and range rule.
- **Whole portal (Playwright):**
  1. Open a section, close it, and the map takes the full width.
  2. Switch on layers from two sections; both appear in the active layers list and the legend.
  3. Select a province, then a district, then step back with the breadcrumb.
  4. Reload the page and get the same view.
  5. Open a `coming-soon` section and see its state.
  6. Start with the backend off and see the full-screen message.

Because the shell has no real data layers, the automated tests use a small test catalogue with two fake `ready` layers, one with `years` and one without, so layer stacking, the legend and the time slider can be exercised.

## Done when

- `npm run dev` starts the portal and opens it in the browser.
- All eight sections open from the rail with the correct state.
- Provinces and districts can be hovered, selected, searched and stepped back through.
- With the test catalogue, layers from two sections stack, reorder, fade and hide, and the time slider appears and disappears by the rule above.
- A reloaded URL restores the same view.
- Every row of the failure handling table can be demonstrated.
- All three test suites pass.

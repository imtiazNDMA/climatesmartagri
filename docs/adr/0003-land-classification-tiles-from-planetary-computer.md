# Land classification tiles come straight from Microsoft Planetary Computer

The annual land classification (Esri / Impact Observatory `io-lulc-annual-v02`, 10 m, 2017–2023) is drawn by the reader's browser from Microsoft Planetary Computer (MPC), not from rasters downloaded to and served by the portal. For each year the backend finds the items that cover Pakistan, checks they cover all of it, registers one MPC mosaic over exactly those item ids, and hands out a tile address for every map layer drawn from it: the full classification, and one class view each for Trees, Rangeland, Bare ground, Crops and Built area, coloured by a one-class colormap. The backend serves only that small answer; the tiles never pass through it.

Per-place figures do not come from MPC at request time. They stay in the prepared `backend/data/land_cover_annual.json`, measured from the same items over HTTP: MPC's statistics service counts against an item's extent rather than a district, and failed with 502 during evaluation.

## Consequences

- The portal now depends on MPC being reachable and on its terms of use. When it is not, only these layers show "Could not load"; figures, charts and every other layer are unaffected.
- The forest, shrub-land and bare-land rasters (about 1.1 GB of converted files) are no longer converted or served, and their layers became class views. The files on disk are the owner's to delete.
- Irrigated and rainfed cropland has no MPC equivalent, so it is the one land raster still served from a local file until a home for it is chosen.
- MPC tiles cover whole item footprints, which reach into India, Afghanistan and Iran. The browser fetches each tile itself, through a `clip://` protocol, and cuts away everything outside Pakistan's outline (`/api/land-cover/outline`) on a canvas before MapLibre draws it. This works on every basemap, which a mask drawn over the map would not. If the outline cannot be loaded, tiles are drawn unclipped.
- The colours of the class views are the MPC classification's own, so a class looks the same in the full map, its class view and the charts.

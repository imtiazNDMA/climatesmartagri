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

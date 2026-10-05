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

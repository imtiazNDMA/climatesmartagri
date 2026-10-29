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


def test_features_that_are_not_objects_are_rejected(tmp_path):
    (tmp_path / "provinces.geojson").write_text('{"type": "FeatureCollection", "features": [42]}', encoding="utf-8")
    with pytest.raises(BoundaryError, match="provinces.geojson"):
        load_places(tmp_path)


def test_features_that_are_not_a_list_are_rejected(tmp_path):
    (tmp_path / "provinces.geojson").write_text('{"type": "FeatureCollection", "features": 7}', encoding="utf-8")
    with pytest.raises(BoundaryError, match="provinces.geojson"):
        load_places(tmp_path)

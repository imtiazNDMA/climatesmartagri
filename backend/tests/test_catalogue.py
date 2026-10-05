import copy
import json

import pytest

from csa_portal.catalogue import CatalogueError, load_catalogue

VALID = {
    "sections": [
        {
            "id": "s1",
            "title": "S1",
            "icon": "trees",
            "order": 1,
            "status": "ready",
            "place_levels": ["national"],
        }
    ],
    "layers": [
        {
            "id": "l1",
            "section_id": "s1",
            "title": "L1",
            "kind": "raster",
            "status": "ready",
            "legend": {
                "type": "classes",
                "items": [{"colour": "#000000", "label": "x"}],
            },
        }
    ],
}


def _load(tmp_path, data):
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return load_catalogue(path)


def _valid():
    return copy.deepcopy(VALID)


def test_valid_catalogue_loads(tmp_path):
    catalogue = _load(tmp_path, _valid())
    assert catalogue.sections[0].id == "s1"
    assert catalogue.sections[0].years is None
    assert catalogue.sections[0].summary == ""
    assert catalogue.layers[0].default_opacity == 1.0


def test_duplicate_section_ids_rejected(tmp_path):
    data = _valid()
    data["sections"].append(copy.deepcopy(data["sections"][0]))
    with pytest.raises(CatalogueError, match="s1"):
        _load(tmp_path, data)


def test_duplicate_layer_ids_rejected(tmp_path):
    data = _valid()
    data["layers"].append(copy.deepcopy(data["layers"][0]))
    with pytest.raises(CatalogueError, match="l1"):
        _load(tmp_path, data)


def test_layer_with_unknown_section_rejected(tmp_path):
    data = _valid()
    data["layers"][0]["section_id"] = "nope"
    with pytest.raises(CatalogueError, match="nope"):
        _load(tmp_path, data)


@pytest.mark.parametrize("bad_id", ["a:b", "a,b", "A b", "Upper", ""])
def test_unsafe_ids_rejected(tmp_path, bad_id):
    data = _valid()
    data["layers"][0]["id"] = bad_id
    with pytest.raises(CatalogueError):
        _load(tmp_path, data)


def test_status_outside_allowed_set_rejected(tmp_path):
    data = _valid()
    data["sections"][0]["status"] = "soon"
    with pytest.raises(CatalogueError):
        _load(tmp_path, data)


def test_reversed_year_range_rejected(tmp_path):
    data = _valid()
    data["sections"][0]["years"] = {"first": 2021, "last": 1994}
    with pytest.raises(CatalogueError):
        _load(tmp_path, data)


def test_non_boundary_layer_needs_legend_and_section(tmp_path):
    data = _valid()
    del data["layers"][0]["legend"]
    with pytest.raises(CatalogueError, match="l1"):
        _load(tmp_path, data)


def test_boundary_layer_needs_neither(tmp_path):
    data = _valid()
    data["layers"].append(
        {"id": "provinces", "title": "Provinces", "kind": "boundary", "status": "ready"}
    )
    catalogue = _load(tmp_path, data)
    assert catalogue.layers[1].section_id is None


def test_missing_file_gives_clear_error(tmp_path):
    with pytest.raises(CatalogueError, match="not found"):
        load_catalogue(tmp_path / "absent.json")


def test_invalid_json_gives_clear_error(tmp_path):
    path = tmp_path / "catalogue.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogueError, match="not valid JSON"):
        load_catalogue(path)

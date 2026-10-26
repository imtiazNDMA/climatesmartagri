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


def test_available_years_load_and_plain_ranges_remain_supported(tmp_path):
    data = _valid()
    data["sections"][0]["years"] = {
        "first": 2017, "last": 2023, "available": [2017, 2019, 2023],
    }
    years = _load(tmp_path, data).sections[0].years
    assert (years.first, years.last, years.available) == (2017, 2023, [2017, 2019, 2023])

    data["sections"][0]["years"] = {"first": 2017, "last": 2023}
    assert _load(tmp_path, data).sections[0].years.available is None


@pytest.mark.parametrize(
    "available",
    [[], [2017, 2017, 2023], [2019, 2017, 2023], [2016, 2017, 2023], [2017, 2023, 2024], [2018, 2023]],
)
def test_invalid_available_years_are_rejected(tmp_path, available):
    data = _valid()
    data["sections"][0]["years"] = {"first": 2017, "last": 2023, "available": available}
    with pytest.raises(CatalogueError, match="available"):
        _load(tmp_path, data)


def test_layer_observations_must_be_available_in_its_section(tmp_path):
    data = _valid()
    data["sections"][0]["years"] = {
        "first": 2017, "last": 2023, "available": [2017, 2019, 2023],
    }
    data["layers"][0]["years"] = {
        "first": 2017, "last": 2023, "available": [2017, 2020, 2023],
    }
    with pytest.raises(CatalogueError, match="l1"):
        _load(tmp_path, data)


def test_temporal_layer_can_be_staged_before_its_section_becomes_temporal(tmp_path):
    data = _valid()
    data["layers"][0]["years"] = {"first": 2017, "last": 2023}
    layer = _load(tmp_path, data).layers[0]
    assert layer.years.observations() == list(range(2017, 2024))


def test_raster_product_requires_years_and_coded_classes(tmp_path):
    data = _valid()
    data["layers"][0]["product"] = {
        "provider": "Provider", "collection": "collection", "version": "v1",
        "resolution_metres": 10, "area_unit": "hectares", "nodata_value": "0",
    }
    with pytest.raises(CatalogueError, match="needs years"):
        _load(tmp_path, data)

    data["layers"][0]["years"] = {"first": 2017, "last": 2023}
    with pytest.raises(CatalogueError, match="without a value"):
        _load(tmp_path, data)


def test_raster_product_rejects_duplicate_class_codes_and_bad_resolution(tmp_path):
    data = _valid()
    layer = data["layers"][0]
    layer["years"] = {"first": 2017, "last": 2023}
    layer["legend"]["items"] = [
        {"colour": "#000000", "label": "First", "value": "1"},
        {"colour": "#ffffff", "label": "Second", "value": "1"},
    ]
    layer["product"] = {
        "provider": "Provider", "collection": "collection", "version": "v1",
        "resolution_metres": 10, "area_unit": "hectares", "nodata_value": "0",
    }
    with pytest.raises(CatalogueError, match="duplicate class"):
        _load(tmp_path, data)

    layer["legend"]["items"][1]["value"] = "2"
    layer["product"]["resolution_metres"] = 0
    with pytest.raises(CatalogueError, match="resolution_metres"):
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


def _geojson_layer():
    return {
        "id": "shapes", "section_id": "s1", "title": "Shapes", "kind": "geojson", "status": "ready",
        "property": "practice",
        "legend": {"type": "classes", "items": [{"colour": "#000000", "label": "Drip", "value": "Drip"}]},
    }


def test_geojson_layer_loads_with_its_property_and_legend_values(tmp_path):
    data = _valid()
    data["layers"].append(_geojson_layer())
    layer = _load(tmp_path, data).layers[1]
    assert layer.kind == "geojson"
    assert layer.property == "practice"
    assert layer.legend.items[0].value == "Drip"


def test_geojson_layer_needs_a_property(tmp_path):
    data = _valid()
    layer = _geojson_layer()
    del layer["property"]
    data["layers"].append(layer)
    with pytest.raises(CatalogueError, match="shapes"):
        _load(tmp_path, data)

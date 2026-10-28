from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
import pytest
from urllib.parse import parse_qsl, urlsplit

from shapely.geometry import box, mapping, shape

from csa_portal.land_cover_mpc import (
    COLLECTION,
    MpcLandCoverError,
    MpcLandCoverResolver,
    country_outline,
    mosaic_tile_url,
    pakistan_geometry,
)


AOI = mapping(box(60, 20, 80, 40))


def item(item_id: str, year: int, *, data: bool = True, bbox=None):
    return {
        "id": item_id,
        "collection": COLLECTION,
        "bbox": bbox or [60, 20, 80, 40],
        "geometry": mapping(box(*(bbox or [60, 20, 80, 40]))),
        "properties": {"start_datetime": f"{year}-01-01T00:00:00Z"},
        "assets": {"data": {"href": f"https://blob.test/{item_id}.tif?sig=secret"}} if data else {},
    }


def response(request: httpx.Request, status: int, body):
    return httpx.Response(status, json=body, request=request)


def resolver(handler, *, now=lambda: 1000.0, ttl=300.0):
    return MpcLandCoverResolver(
        httpx.Client(transport=httpx.MockTransport(handler)), AOI, now=now, cache_ttl_seconds=ttl
    )


def registered(request: httpx.Request, search_id: str = "pc1.1.abc"):
    return response(request, 200, {"searchid": search_id, "links": []})


def test_resolve_registers_one_mosaic_over_exactly_the_years_items():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/search"):
            return response(request, 200, {"type": "FeatureCollection", "features": [
                item("42Q-2018", 2018, bbox=[60, 20, 70, 40]),
                item("42Q-2019", 2019, bbox=[60, 20, 70, 40]),
                item("43Q-2019", 2019, bbox=[70, 20, 80, 40]),
            ]})
        return registered(request)

    result = resolver(handler).resolve(2019)
    assert result.year == 2019
    assert result.search_id == "pc1.1.abc"
    assert result.item_ids == ("42Q-2019", "43Q-2019")
    assert result.bounds == (60.0, 20.0, 80.0, 40.0)
    assert result.collection == COLLECTION
    assert result.attribution.startswith("Esri")
    assert "secret" not in json.dumps(result.as_dict())
    register = [request for request in seen if request.url.path.endswith("/mosaic/register")]
    assert len(register) == 1
    body = json.loads(register[0].content)
    assert body["collections"] == [COLLECTION]
    assert body["filter"] == {"op": "in", "args": [{"property": "id"}, ["42Q-2019", "43Q-2019"]]}
    assert not any("tilejson" in str(request.url) for request in seen)


def test_resolve_caches_then_refreshes_after_ttl():
    calls = 0
    clock = [1000.0]

    def handler(request):
        nonlocal calls
        calls += 1
        if request.url.path.endswith("/search"):
            return response(request, 200, {"features": [item("42Q-2020", 2020)]})
        return registered(request, f"pc1.{calls}.abc")

    service = resolver(handler, now=lambda: clock[0], ttl=60)
    first = service.resolve(2020)
    assert service.resolve(2020) is first
    assert calls == 2
    clock[0] = 1061
    assert service.resolve(2020).search_id != first.search_id
    assert calls == 4


def test_invalidate_forces_one_year_to_refresh():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if request.url.path.endswith("/search"):
            return response(request, 200, {"features": [item("42Q-2021", 2021)]})
        return registered(request)

    service = resolver(handler)
    service.resolve(2021)
    service.invalidate(2021)
    service.resolve(2021)
    assert calls == 4


@pytest.mark.parametrize("year", [2016, 2024])
def test_unsupported_year_is_rejected_without_an_upstream_call(year):
    def handler(_request):
        raise AssertionError("upstream should not be called")

    with pytest.raises(MpcLandCoverError, match="unsupported year") as caught:
        resolver(handler).resolve(year)
    assert caught.value.code == "year-out-of-range"


def test_duplicate_ids_missing_assets_and_incomplete_coverage_are_rejected():
    cases = [
        ([item("same", 2019), item("same", 2019)], "duplicate item", "invalid-source"),
        ([item("missing", 2019, data=False)], "no data asset", "invalid-source"),
        ([item("west", 2019, bbox=[60, 20, 65, 40])], "cover Pakistan", "incomplete-source"),
    ]
    for features, message, code in cases:
        def handler(request, features=features):
            return response(request, 200, {"features": features})

        with pytest.raises(MpcLandCoverError, match=message) as caught:
            resolver(handler).resolve(2019)
        assert caught.value.code == code


@pytest.mark.parametrize(
    ("failure", "code"),
    [(httpx.ReadTimeout("slow"), "upstream-timeout"), (httpx.ConnectError("down"), "upstream-unavailable")],
)
def test_network_failures_are_typed(failure, code):
    def handler(_request):
        raise failure

    with pytest.raises(MpcLandCoverError) as caught:
        resolver(handler).resolve(2020)
    assert caught.value.code == code


def test_malformed_stac_is_rejected():
    def bad_stac(request):
        return response(request, 200, {"not_features": []})

    with pytest.raises(MpcLandCoverError) as caught:
        resolver(bad_stac).resolve(2020)
    assert caught.value.code == "invalid-upstream-response"



def test_stac_pagination_is_followed_and_combined_deterministically():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/search") and len(calls) == 1:
            return response(request, 200, {
                "features": [item("west", 2020, bbox=[60, 20, 70, 40])],
                "links": [{
                    "rel": "next",
                    "href": "https://planetarycomputer.microsoft.com/api/stac/v1/search",
                    "method": "POST",
                    "body": {"token": "next-page"},
                }],
            })
        if request.url.path.endswith("/search"):
            assert json.loads(request.content) == {"token": "next-page"}
            return response(request, 200, {
                "features": [item("east", 2020, bbox=[70, 20, 80, 40])], "links": [],
            })
        return registered(request)

    assert resolver(handler).resolve(2020).item_ids == ("east", "west")


def test_a_cached_year_does_not_register_again():
    registrations = 0

    def handler(request):
        nonlocal registrations
        if request.url.path.endswith("/search"):
            return response(request, 200, {"features": [item("42Q-2019", 2019)]})
        registrations += 1
        return registered(request)

    service = resolver(handler)
    service.resolve(2019)
    service.resolve(2019)
    assert registrations == 1


@pytest.mark.parametrize(
    ("status", "code"),
    [(503, "upstream-unavailable"), (429, "upstream-unavailable"), (400, "upstream-rejected")],
)
def test_a_failed_registration_has_a_stable_error_code(status, code):
    def handler(request):
        if request.url.path.endswith("/search"):
            return response(request, 200, {"features": [item("42Q-2020", 2020)]})
        return response(request, status, {"message": "no"})

    with pytest.raises(MpcLandCoverError) as caught:
        resolver(handler).resolve(2020)
    assert caught.value.code == code


def test_a_registration_that_times_out_is_an_upstream_timeout():
    def handler(request):
        if request.url.path.endswith("/search"):
            return response(request, 200, {"features": [item("42Q-2020", 2020)]})
        raise httpx.ReadTimeout("slow")

    with pytest.raises(MpcLandCoverError) as caught:
        resolver(handler).resolve(2020)
    assert caught.value.code == "upstream-timeout"


@pytest.mark.parametrize("body", [{}, {"searchid": ""}, {"searchid": 7}, {"searchid": "../../x"}, {"searchid": "a b"}, {"searchid": "pc1.1.abc\n"}])
def test_an_unusable_search_id_is_an_invalid_upstream_response(body):
    def handler(request):
        if request.url.path.endswith("/search"):
            return response(request, 200, {"features": [item("42Q-2020", 2020)]})
        return response(request, 200, body)

    with pytest.raises(MpcLandCoverError) as caught:
        resolver(handler).resolve(2020)
    assert caught.value.code == "invalid-upstream-response"


def test_mosaic_tile_url_keeps_placeholders_and_encodes_the_colormap():
    url = mosaic_tile_url("pc1.1.abc", {5: "#e49635", 2: "#397d49"})

    assert url.startswith(
        "https://planetarycomputer.microsoft.com/api/data/v1/mosaic/pc1.1.abc/tiles/WebMercatorQuad/{z}/{x}/{y}@1x.png?"
    )
    query = dict(parse_qsl(urlsplit(url).query))
    assert query["collection"] == COLLECTION
    assert query["assets"] == "data"
    assert json.loads(query["colormap"]) == {"2": [57, 125, 73, 255], "5": [228, 150, 53, 255]}
    assert not {"sig", "se", "sp", "sv", "st"} & {key.lower() for key in query}


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "upstream-rejected"),
        (429, "upstream-unavailable"),
        (500, "upstream-unavailable"),
        (503, "upstream-unavailable"),
    ],
)
def test_http_statuses_map_to_actionable_codes(status, code):
    def handler(request):
        return response(request, status, {"message": "no"})

    with pytest.raises(MpcLandCoverError) as caught:
        resolver(handler).resolve(2020)
    assert caught.value.code == code


def test_pakistan_geometry_is_read_and_repaired_from_the_prepared_boundaries(tmp_path):
    (tmp_path / "provinces.geojson").write_text(
        json.dumps({
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {}, "geometry": mapping(box(60, 20, 70, 30))},
                {"type": "Feature", "properties": {}, "geometry": mapping(box(70, 20, 80, 30))},
            ],
        }),
        encoding="utf-8",
    )
    geometry = pakistan_geometry(tmp_path)
    assert geometry["type"] in {"Polygon", "MultiPolygon"}
    assert geometry["coordinates"]


def test_pakistan_geometry_reports_missing_or_empty_boundaries(tmp_path):
    with pytest.raises(MpcLandCoverError) as caught:
        pakistan_geometry(tmp_path)
    assert caught.value.code == "invalid-boundaries"

    (tmp_path / "provinces.geojson").write_text(json.dumps({"type": "FeatureCollection"}), encoding="utf-8")
    with pytest.raises(MpcLandCoverError) as caught:
        pakistan_geometry(tmp_path)
    assert caught.value.code == "invalid-boundaries"


def test_the_country_outline_closes_slivers_between_provinces_and_drops_pinholes():
    # Two provinces that should touch, 5 m apart, and a pinhole left inside one of them.
    west = box(60, 20, 70, 30).difference(box(65, 25, 65.00001, 25.00001))
    east = box(70.00005, 20, 80, 30)
    outline = shape(country_outline(mapping(west.union(east))))

    assert outline.geom_type == "Polygon"
    assert outline.is_valid
    assert list(outline.interiors) == []
    assert abs(outline.area - 200) / 200 < 1e-4
    assert outline.covers(box(69.9, 24, 70.1, 26))

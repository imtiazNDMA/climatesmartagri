from pathlib import Path
from types import SimpleNamespace
from datetime import datetime

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from csa_portal.hazards import DistrictRiskService, classify_risk, district_values, load_hazards
from csa_portal.places import PlaceIndex
from csa_portal.main import create_app


def test_hazard_products_are_versioned_and_ordered(settings):
    registry = load_hazards(settings.hazard_products_path)
    assert registry.classification == "forecast-guidance"
    assert registry.threshold_version
    assert [product.id for product in registry.products] == [
        "frost", "heat-stress", "heavy-rain", "strong-wind", "low-visibility"
    ]
    assert [band.threshold for band in registry.products[0].bands] == [3, 12, 24]


def test_hazard_products_api(settings):
    response = TestClient(create_app(settings)).get("/api/hazards/products")
    assert response.status_code == 200
    body = response.json()
    assert body["classification"] == "forecast-guidance"
    assert body["products"][0]["forecast_layer"] == "frost-degree-hours"
    assert "not an official warning" in body["disclaimer"].lower()


def test_district_risk_api_is_present_without_a_forecast_source(settings):
    response = TestClient(create_app(settings)).get(
        "/api/hazards/district-risk",
        params={
            "hazard": "frost",
            "model": "model-a",
            "level": 0,
            "time": "2026101406",
            "run": "2026101400",
        },
    )
    assert response.status_code == 501
    assert response.json()["detail"]["reason"] == "not-configured"


def test_risk_classes_follow_above_and_below_thresholds(settings):
    products = {product.id: product for product in load_hazards(settings.hazard_products_path).products}
    frost = products["frost"]
    fog = products["low-visibility"]

    assert [classify_risk(frost, value) for value in [2.9, 3, 12, 24]] == [None, "low", "medium", "high"]
    assert [classify_risk(fog, value) for value in [6, 5, 2, 1]] == [None, "low", "medium", "high"]


def test_district_values_use_the_requested_tail_percentile(tmp_path: Path):
    path = tmp_path / "values.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=4,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 2, 1, 1),
        nodata=float("nan"),
    ) as target:
        target.write(np.array([[1, 2, 10, 20], [3, 4, 30, 40]], dtype="float32"), 1)
    features = [
        {
            "type": "Feature",
            "properties": {"id": "west", "name": "West"},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "east", "name": "East"},
            "geometry": {"type": "Polygon", "coordinates": [[[2, 0], [4, 0], [4, 2], [2, 2], [2, 0]]]},
        },
    ]

    high_tail = district_values(path, features, 90)
    low_tail = district_values(path, features, 10)

    assert high_tail == [("west", "West", 3.7), ("east", "East", 37.0)]
    assert low_tail == [("west", "West", 1.3), ("east", "East", 13.0)]


def test_district_risk_service_returns_semantic_classes_and_colours(settings, tmp_path: Path):
    path = tmp_path / "risk.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=3,
        height=1,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 1, 1, 1),
        nodata=float("nan"),
    ) as target:
        target.write(np.array([[4, 13, 25]], dtype="float32"), 1)
    features = [
        {
            "type": "Feature",
            "properties": {"id": f"d{index}", "name": f"District {index}"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[index, 0], [index + 0.9, 0], [index + 0.9, 1], [index, 1], [index, 0]]],
            },
        }
        for index in range(3)
    ]
    places = PlaceIndex(places=[], boundaries={"district": {"features": features}}, loaded=True)
    calls = 0

    def value_file(*_args):
        nonlocal calls
        calls += 1
        return path

    provider = SimpleNamespace(value_file=value_file)
    service = DistrictRiskService(load_hazards(settings.hazard_products_path), places, provider, None)

    body = service.calculate("frost", "model-a", 0, datetime(2026, 10, 14, 6), datetime(2026, 10, 14))

    assert [district["risk"] for district in body["districts"]] == ["low", "medium", "high"]
    assert body["colours"] == {"low": "#facc15", "medium": "#f97316", "high": "#dc2626"}
    assert body["statistic"]["percentile"] == 90
    assert service.calculate(
        "frost", "model-a", 0, datetime(2026, 10, 14, 6), datetime(2026, 10, 14)
    ) == body
    assert calls == 1

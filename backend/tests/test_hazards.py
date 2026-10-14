from fastapi.testclient import TestClient

from csa_portal.hazards import load_hazards
from csa_portal.main import create_app


def test_hazard_products_are_versioned_and_ordered(settings):
    registry = load_hazards(settings.hazard_products_path)
    assert registry.classification == "forecast-guidance"
    assert registry.threshold_version
    assert [product.id for product in registry.products] == [
        "frost", "heat-stress", "heavy-rain", "strong-wind", "low-visibility"
    ]
    assert [band.threshold for band in registry.products[0].bands] == [2, 0, -2]


def test_hazard_products_api(settings):
    response = TestClient(create_app(settings)).get("/api/hazards/products")
    assert response.status_code == 200
    body = response.json()
    assert body["classification"] == "forecast-guidance"
    assert body["products"][0]["forecast_layer"] == "temperature-min"
    assert "not an official warning" in body["disclaimer"].lower()

from fastapi.testclient import TestClient

from csa_portal.catalogue import load_catalogue
from csa_portal.main import create_app
from csa_portal.settings import BACKEND_DIR, Settings

EXPECTED = [
    ("land-cover", "no-data"),
    ("irrigation", "no-data"),
    ("emissions", "no-data"),
    ("water-balance", "no-data"),
    ("food-security", "no-data"),
    ("climate-calendar", "no-data"),
    ("hazards", "coming-soon"),
    ("exposure", "coming-soon"),
]


def test_shipped_catalogue_is_valid_and_complete():
    catalogue = load_catalogue(BACKEND_DIR / "catalogue.json")
    ordered = sorted(catalogue.sections, key=lambda s: s.order)
    assert [(s.id, s.status) for s in ordered] == EXPECTED
    assert [s.order for s in ordered] == list(range(1, 9))
    assert all(s.summary for s in ordered if s.status == "coming-soon")
    boundary_ids = {layer.id for layer in catalogue.layers if layer.kind == "boundary"}
    assert boundary_ids == {"provinces", "districts"}
    assert all(
        layer.status == "no-data" for layer in catalogue.layers if layer.kind != "boundary"
    )


def test_shell_routes_return_no_data_or_coming_soon(tmp_path):
    settings = Settings(BACKEND_DIR / "catalogue.json", tmp_path, "https://example.test/s.json")
    client = TestClient(create_app(settings))
    for section_id, status in EXPECTED:
        response = client.get(f"/api/sections/{section_id}/data")
        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == status
    tile = client.get("/api/tiles/forest/0/0/0")
    assert tile.json()["detail"]["reason"] == "no-data"

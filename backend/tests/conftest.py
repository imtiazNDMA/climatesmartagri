from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from csa_portal.main import create_app
from csa_portal.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def fake_section(place, year):
    return {
        "figures": [{"label": "Place", "value": place.id, "unit": ""}],
        "charts": [],
        "notes": ["A note"],
    }


def fake_shapes():
    return {"type": "FeatureCollection", "features": []}


def fake_tile(z, x, y, year):
    return (f"tile-{z}-{x}-{y}-{year}".encode(), "image/png")


@pytest.fixture
def settings():
    return Settings(
        catalogue_path=FIXTURES / "test_catalogue.json",
        boundaries_dir=FIXTURES / "boundaries",
        basemap_style_url="https://example.test/style.json",
        data_dir=FIXTURES / "no-data-here",
    )


@pytest.fixture
def client(settings):
    app = create_app(
        settings,
        section_providers={"alpha-section": fake_section, "beta-section": fake_section},
        tile_providers={"fake-yearly": fake_tile},
        geojson_providers={"fake-shapes": fake_shapes},
    )
    return TestClient(app)


@pytest.fixture
def bare_client(settings):
    """The app with no providers registered."""
    return TestClient(create_app(settings, section_providers={}, tile_providers={}, geojson_providers={}))

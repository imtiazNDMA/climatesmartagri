import io
from dataclasses import replace

from fastapi.testclient import TestClient
from PIL import Image

from csa_portal.crop_classification import ClassificationResult, Prediction
from csa_portal.main import create_app


class FakeClassifier:
    configured = True

    def __init__(self):
        self.calls = []

    def classify(self, image: bytes, crop: str, top_k: int) -> ClassificationResult:
        self.calls.append((image, crop, top_k))
        return ClassificationResult(
            predictions=[Prediction(
                label_index=21,
                canonical_class_id="RICE_HEALTHY_001",
                canonical_class="Healthy rice",
                crop="Rice",
                category="healthy",
                confidence=0.92,
            )],
            needs_expert_review=False,
        )


def image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (40, 30), "green").save(output, format="PNG")
    return output.getvalue()


def test_predict_validates_and_returns_ranked_result(settings):
    classifier = FakeClassifier()
    client = TestClient(create_app(settings, crop_classifier=classifier))
    response = client.post(
        "/api/crop-classification/predict",
        data={"crop": "Rice", "top_k": "3"},
        files={"image": ("leaf.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["predictions"][0]["canonical_class_id"] == "RICE_HEALTHY_001"
    assert classifier.calls[0][1:] == ("Rice", 3)


def test_predict_rejects_wrong_media_type(settings):
    client = TestClient(create_app(settings, crop_classifier=FakeClassifier()))
    response = client.post(
        "/api/crop-classification/predict",
        data={"crop": "Rice", "top_k": "3"},
        files={"image": ("leaf.txt", b"not an image", "text/plain")},
    )
    assert (response.status_code, response.json()["detail"]["reason"]) == (415, "unsupported-image-type")


def test_predict_rejects_corrupt_image(settings):
    client = TestClient(create_app(settings, crop_classifier=FakeClassifier()))
    response = client.post(
        "/api/crop-classification/predict",
        data={"crop": "Maize", "top_k": "3"},
        files={"image": ("leaf.png", b"not an image", "image/png")},
    )
    assert (response.status_code, response.json()["detail"]["reason"]) == (422, "invalid-image")


def test_predict_reports_unconfigured_model(settings, tmp_path):
    client = TestClient(create_app(replace(settings, crop_model_dir=tmp_path)))
    status = client.get("/api/crop-classification/status").json()
    assert status["configured"] is False
    response = client.post(
        "/api/crop-classification/predict",
        data={"crop": "Rice", "top_k": "3"},
        files={"image": ("leaf.png", image_bytes(), "image/png")},
    )
    assert (response.status_code, response.json()["detail"]["reason"]) == (503, "classifier-unavailable")

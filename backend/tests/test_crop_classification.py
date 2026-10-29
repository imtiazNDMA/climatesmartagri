import io
from dataclasses import replace

from fastapi.testclient import TestClient
from PIL import Image

import json

from csa_portal.crop_classification import ClassificationResult, CropClassifier, CropClassifierRouter, Prediction
from csa_portal.main import create_app


class FakeClassifier:
    configured = True
    crops = ["Rice", "Maize", "Cotton", "Wheat", "Sugarcane"]

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
    client = TestClient(create_app(replace(settings, crop_model_dir=tmp_path, five_crop_model_dir=tmp_path)))
    status = client.get("/api/crop-classification/status").json()
    assert status["configured"] is False
    response = client.post(
        "/api/crop-classification/predict",
        data={"crop": "Rice", "top_k": "3"},
        files={"image": ("leaf.png", image_bytes(), "image/png")},
    )
    assert (response.status_code, response.json()["detail"]["reason"]) == (503, "classifier-unavailable")


def package(directory, calibrated=None, review_threshold=None):
    directory.mkdir()
    for name in ("model.ts", "label_map.json", "portal_inference.py"):
        (directory / name).write_text("", encoding="utf-8")
    config = {}
    if calibrated is not None:
        config["confidence_calibrated"] = calibrated
    if review_threshold is not None:
        config["review_threshold"] = review_threshold
    if config:
        (directory / "inference_config.json").write_text(json.dumps(config))
    return directory


class FakePredictor:
    def __init__(self, crop):
        self.crop = crop

    def predict(self, image, crop, top_k):
        return [{
            "label_index": 0, "canonical_class_id": f"{crop.lower()}_healthy",
            "canonical_class": f"Healthy ({crop.lower()})", "crop": crop, "category": "healthy", "confidence": 0.5,
        }]


def loaded(classifier, crop):
    classifier._predictor = FakePredictor(crop)
    return classifier


def test_each_crop_goes_to_the_package_that_serves_it(tmp_path):
    rice_maize = loaded(CropClassifier(package(tmp_path / "improved-002"), ("Rice", "Maize")), "Rice")
    five_crop = loaded(CropClassifier(package(tmp_path / "five-crop-001", calibrated=False), ("Cotton", "Wheat", "Sugarcane")), "Wheat")
    router = CropClassifierRouter([rice_maize, five_crop])

    assert router.crops == ["Rice", "Maize", "Cotton", "Wheat", "Sugarcane"]
    assert router.classify(image_bytes(), "Rice", 3).model == "improved-002"
    wheat = router.classify(image_bytes(), "Wheat", 3)
    assert (wheat.model, wheat.predictions[0].crop, wheat.calibrated) == ("five-crop-001", "Wheat", False)
    assert wheat.needs_expert_review is True


def test_calibrated_is_true_only_when_the_package_says_so(tmp_path):
    classifier = loaded(CropClassifier(package(tmp_path / "calibrated", calibrated=True), ("Cotton",)), "Cotton")

    assert classifier.classify(image_bytes(), "Cotton", 1).calibrated is True


def test_a_crop_whose_package_is_missing_is_unavailable_while_others_work(settings, tmp_path):
    client = TestClient(create_app(replace(settings, five_crop_model_dir=tmp_path / "missing")))

    status = client.get("/api/crop-classification/status").json()
    response = client.post(
        "/api/crop-classification/predict",
        data={"crop": "Cotton", "top_k": "3"},
        files={"image": ("leaf.png", image_bytes(), "image/png")},
    )

    assert status["crops"] == ["Rice", "Maize"]
    assert (response.status_code, response.json()["detail"]["reason"]) == (503, "classifier-unavailable")


def test_a_calibrated_package_sets_its_own_review_threshold(tmp_path):
    lenient = loaded(CropClassifier(package(tmp_path / "lenient", calibrated=True, review_threshold=0.45), ("Wheat",)), "Wheat")
    default = loaded(CropClassifier(package(tmp_path / "default"), ("Wheat",)), "Wheat")

    # FakePredictor answers with confidence 0.5: above 0.45, below the 0.65 default.
    assert lenient.classify(image_bytes(), "Wheat", 1).needs_expert_review is False
    assert default.classify(image_bytes(), "Wheat", 1).needs_expert_review is True

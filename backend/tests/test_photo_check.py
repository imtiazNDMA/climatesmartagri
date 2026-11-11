"""The photo check: the vision model says whether a photo is a plant, which crop it is and whether it is usable,
before a classifier is asked. The classifier still makes the disease call."""

import hashlib
import io

from fastapi.testclient import TestClient
from PIL import Image

from csa_portal.ai.model import Completion, ModelError, ScriptedModel
from csa_portal.ai.tracing import Tracer
from csa_portal.crop_classification import ClassificationResult, Prediction
from csa_portal.main import create_app
from csa_portal.photo_check import PhotoReading
from csa_portal.settings import Settings


class FakeClassifier:
    configured = True
    crops = ["Rice", "Maize", "Cotton", "Wheat", "Sugarcane"]

    def __init__(self, confidence=0.92):
        self.calls = []
        self.confidence = confidence

    def classify(self, image: bytes, crop: str, top_k: int) -> ClassificationResult:
        self.calls.append(crop)
        return ClassificationResult(
            predictions=[Prediction(
                label_index=1, canonical_class_id=f"{crop.upper()}_HEALTHY_001", canonical_class=f"Healthy {crop.lower()}",
                crop=crop, category="healthy", confidence=self.confidence,
            )],
            needs_expert_review=False,
        )


class DownModel:
    """LM Studio switched off, or too slow to answer in the time allowed."""

    def complete(self, messages, tools=None, output=None, image=None):
        raise ModelError(503, "assistant-unavailable", "The local AI model could not be reached")


def leaf() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (40, 30), "green").save(output, format="PNG")
    return output.getvalue()


def reading(**fields) -> Completion:
    return Completion(data=PhotoReading(**{"is_plant": True, "crop": "Maize", **fields}))


def portal(settings, model, classifier=None, tracer=None):
    classifier = classifier or FakeClassifier()
    app = create_app(settings, crop_classifier=classifier, photo_check_model=model, tracer=tracer)
    return TestClient(app), classifier


def post(client, path, crop):
    return client.post(
        f"/api/crop-classification/{path}", data={"crop": crop}, files={"image": ("leaf.png", leaf(), "image/png")}
    )


def test_auto_classifies_as_the_crop_the_photo_check_names(settings):
    model = ScriptedModel([reading(crop="Maize")])
    client, classifier = portal(settings, model)

    body = post(client, "predict", "Auto").json()

    assert classifier.calls == ["Maize"]
    assert body["crop"] == "Maize"
    assert body["predictions"][0]["canonical_class_id"] == "MAIZE_HEALTHY_001"
    assert body["photo_check"] == {
        "status": "passed", "identified_crop": "Maize", "looks_like": None, "crop_mismatch": False, "quality": [],
    }
    assert body["needs_expert_review"] is False
    assert model.images[0].sha256 == hashlib.sha256(leaf()).hexdigest()


def test_a_photo_that_is_not_a_plant_is_not_classified(settings):
    client, classifier = portal(settings, ScriptedModel([reading(is_plant=False, crop="Other", other_plant="a bicycle")]))

    response = post(client, "predict", "Auto")

    assert response.status_code == 200
    body = response.json()
    assert classifier.calls == []
    assert (body["predictions"], body["crop"], body["guidance"]) == ([], None, None)
    assert body["photo_check"]["status"] == "not-a-plant"


def test_a_plant_outside_the_five_crops_is_not_classified_in_auto_and_says_what_it_looks_like(settings):
    client, classifier = portal(settings, ScriptedModel([reading(crop="Other", other_plant="Tomato")]))

    body = post(client, "predict", "Auto").json()

    assert classifier.calls == []
    assert body["predictions"] == []
    assert (body["photo_check"]["status"], body["photo_check"]["looks_like"]) == ("unsupported-crop", "Tomato")


def test_a_leaf_the_check_cannot_tell_between_crops_is_left_for_the_reader_to_name(settings):
    client, classifier = portal(settings, ScriptedModel([reading(crop="Unclear")]))

    body = post(client, "predict", "Auto").json()

    assert classifier.calls == []
    assert body["photo_check"]["status"] == "crop-unclear"


def test_a_poor_photo_is_still_classified_but_always_goes_to_expert_review(settings):
    model = ScriptedModel([reading(crop="Wheat", blurred=True, several_leaves=True)])
    client, classifier = portal(settings, model, FakeClassifier(confidence=0.99))

    body = post(client, "predict", "Auto").json()

    assert classifier.calls == ["Wheat"]
    assert body["photo_check"]["quality"] == ["blurred", "several-leaves"]
    assert body["needs_expert_review"] is True


def test_auto_says_so_when_the_model_cannot_be_reached_so_the_reader_can_pick_the_crop(settings):
    client, classifier = portal(settings, DownModel())

    response = post(client, "predict", "Auto")

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "photo-check-unavailable"
    assert classifier.calls == []


def test_a_hand_picked_crop_is_classified_without_asking_the_model(settings):
    model = ScriptedModel([])
    client, classifier = portal(settings, model)

    body = post(client, "predict", "Rice").json()

    assert classifier.calls == ["Rice"]
    assert body["photo_check"] is None
    assert model.sent == []


def test_a_hand_picked_crop_can_be_checked_and_a_different_crop_is_a_warning(settings):
    client, classifier = portal(settings, ScriptedModel([reading(crop="Maize", too_dark=True), reading(crop="Rice")]))

    differs = post(client, "check", "Rice").json()
    agrees = post(client, "check", "Rice").json()

    assert differs == {
        "status": "passed", "identified_crop": "Maize", "looks_like": None, "crop_mismatch": True, "quality": ["too-dark"],
    }
    assert agrees["crop_mismatch"] is False
    assert classifier.calls == []


def test_checking_a_hand_picked_crop_does_not_call_an_unclear_leaf_a_mismatch(settings):
    client, _ = portal(settings, ScriptedModel([reading(crop="Unclear")]))

    body = post(client, "check", "Rice").json()

    assert (body["status"], body["crop_mismatch"]) == ("crop-unclear", False)


def test_status_says_whether_auto_is_offered(settings):
    on, _ = portal(settings, ScriptedModel([]))
    off = TestClient(create_app(settings, crop_classifier=FakeClassifier()))

    assert on.get("/api/crop-classification/status").json()["auto"] is True
    assert off.get("/api/crop-classification/status").json()["auto"] is False


def test_with_the_photo_check_off_auto_is_refused_and_a_hand_picked_crop_works_as_before(settings):
    classifier = FakeClassifier()
    client = TestClient(create_app(settings, crop_classifier=classifier))

    assert post(client, "predict", "Auto").json()["detail"]["reason"] == "photo-check-unavailable"
    assert post(client, "check", "Rice").json()["detail"]["reason"] == "photo-check-unavailable"
    assert post(client, "predict", "Rice").json()["predictions"][0]["crop"] == "Rice"


def test_the_photo_check_is_off_unless_the_deployment_turns_it_on():
    assert Settings._from({}).photo_check is False
    turned_on = Settings._from({"CSA_PHOTO_CHECK": "1", "CSA_PHOTO_CHECK_TIMEOUT": "12"})
    assert (turned_on.photo_check, turned_on.photo_check_timeout) == (True, 12)
    assert Settings._from({}).photo_check_timeout == 30


def test_a_photo_check_leaves_a_trace_that_says_what_the_photo_was_and_what_the_model_read(settings):
    class Sink:
        def __init__(self):
            self.traces = []

        def write_trace(self, trace):
            self.traces.append(trace)

    sink = Sink()
    client, _ = portal(settings, ScriptedModel([reading(crop="Cotton")]), tracer=Tracer(sink, capture_content=True))

    post(client, "predict", "Auto")

    trace = sink.traces[0]
    assert (trace.agent, trace.status) == ("photo-check", "ok")
    assert trace.answer_text == '{"status":"passed","identified_crop":"Cotton","looks_like":null,"crop_mismatch":false,"quality":[]}'
    assert trace.spans[0].attributes["csa.image.sha256"] == hashlib.sha256(leaf()).hexdigest()

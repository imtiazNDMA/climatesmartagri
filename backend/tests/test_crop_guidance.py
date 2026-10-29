import json
from pathlib import Path

from csa_portal.crop_guidance import CropGuidance

BACKEND = Path(__file__).resolve().parents[1]


def guidance_file(tmp_path, status="review-pending", reviewer=None):
    path = tmp_path / "crop_guidance.json"
    path.write_text(json.dumps({
        "version": "draft-test",
        "source": "test guide",
        "status": status,
        "reviewer": reviewer,
        "classes": {
            "rice_blast": {
                "aliases": ["RICE_DISEASE_004"],
                "name": "Rice Blast",
                "type": "Fungal disease",
                "symptoms": ["Diamond-shaped lesions"],
                "treatment_steps": ["Apply a labeled fungicide."],
                "prevention": ["Balance nitrogen."],
                "chemical_prevention": ["Use fungicide-treated seed."],
            }
        },
    }))
    return path


def test_unreviewed_guidance_withholds_treatment_steps_and_chemical_prevention(tmp_path):
    guidance = CropGuidance(guidance_file(tmp_path)).for_class("rice_blast")

    assert guidance.symptoms == ["Diamond-shaped lesions"]
    assert guidance.prevention == ["Balance nitrogen."]
    assert guidance.treatment_steps == []
    assert guidance.reviewed is False


def test_reviewed_guidance_shows_everything(tmp_path):
    guidance = CropGuidance(guidance_file(tmp_path, status="reviewed", reviewer="Agronomist")).for_class("rice_blast")

    assert guidance.treatment_steps == ["Apply a labeled fungicide."]
    assert guidance.prevention == ["Balance nitrogen.", "Use fungicide-treated seed."]
    assert guidance.reviewed is True


def test_a_reviewed_status_without_a_named_reviewer_does_not_count(tmp_path):
    guidance = CropGuidance(guidance_file(tmp_path, status="reviewed")).for_class("rice_blast")

    assert guidance.treatment_steps == []


def test_improved_002_classes_find_guidance_through_aliases(tmp_path):
    guidance = CropGuidance(guidance_file(tmp_path))

    assert guidance.for_class("RICE_DISEASE_004").name == "Rice Blast"
    assert guidance.for_class("RICE_PEST_002") is None


def test_every_five_crop_class_has_guidance_in_the_shipped_file():
    labels = json.loads((BACKEND / "models" / "crop-classification" / "five-crop-001" / "label_map.json").read_text())
    guidance = CropGuidance(BACKEND / "crop_guidance.json")

    missing = [item["canonical_class_id"] for item in labels["classes"] if guidance.for_class(item["canonical_class_id"]) is None]

    assert missing == []
    assert guidance.reviewed is False

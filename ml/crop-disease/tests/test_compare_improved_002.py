import pytest

from compare_improved_002 import OTHER, matched_images, original_name, score, to_shared


def ours(path, label, split="test", crop="Rice", status="kept"):
    return {"path": path, "label": label, "split": split, "crop": crop, "status": status}


def theirs(path, class_id, split="test"):
    return {"project_relative_path": path, "canonical_class_id": class_id, "split": split}


def test_original_name_drops_the_source_prefixes():
    assert original_name("data/raw/Rice_Maize/rice/Tungro/20k_train_TUNGRO1_214.JPG") == "tungro1_214.jpg"
    assert original_name("Train/Rice_Tungro/TUNGRO1_214.jpg") == "tungro1_214.jpg"


def test_an_image_matches_only_when_both_hold_it_out_with_the_same_class():
    manifest = [
        ours("Train/Rice_Tungro/TUNGRO1_1.jpg", "rice_tungro"),
        ours("Train/Rice_Tungro/TUNGRO1_2.jpg", "rice_tungro", split="train"),
        ours("Train/Rice_Tungro/TUNGRO1_3.jpg", "rice_tungro"),
        ours("Train/Rice_Blast/BLAST1_4.jpg", "rice_blast"),
        ours("Train/maize_stem_borer/00000001.jpg", "maize_stem_borer", crop="Maize"),
    ]
    holdout = [
        theirs("raw/20k_train_TUNGRO1_1.jpg", "RICE_DISEASE_006"),
        theirs("raw/20k_train_TUNGRO1_2.jpg", "RICE_DISEASE_006"),
        theirs("raw/20k_train_TUNGRO1_3.jpg", "RICE_DISEASE_006", split="train"),
        theirs("raw/20k_train_BLAST1_4.jpg", "RICE_DISEASE_002"),
        theirs("raw/00000001.jpg", "MAIZE_PEST_004"),
    ]

    assert matched_images(manifest, holdout, "test") == {"Train/Rice_Tungro/TUNGRO1_1.jpg": ("Rice", "rice_tungro")}


def test_improved_002_classes_map_onto_ours_and_everything_else_is_other():
    assert to_shared("RICE_DISEASE_005") == "rice_blast"
    assert to_shared("RICE_PEST_002") == OTHER


def test_score_counts_a_prediction_outside_the_shared_classes_as_wrong():
    truth = {"a": "rice_blast", "b": "rice_blast", "c": "rice_tungro"}
    predicted = {"a": "rice_blast", "b": OTHER, "c": "rice_tungro"}

    result = score(truth, predicted)

    assert result["accuracy"] == pytest.approx(2 / 3)
    assert result["macro_f1"] == pytest.approx((2 / 3 + 1) / 2)
    assert set(result["per_class"]) == {"rice_blast", "rice_tungro"}

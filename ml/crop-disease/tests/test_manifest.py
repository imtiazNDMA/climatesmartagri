from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from crop_disease.manifest import Taxonomy, build_manifest, write_manifest

PROJECT = Path(__file__).resolve().parents[1]


def textured(seed: int, brightness: int = 0) -> Image.Image:
    """A smooth random pattern: distinct seeds look different, brightening keeps its shape."""
    rng = np.random.default_rng(seed)
    coarse = rng.integers(0, 200, size=(8, 8, 3)).astype(np.uint8)
    image = Image.fromarray(coarse).resize((96, 96), Image.BICUBIC)
    return Image.fromarray(np.clip(np.asarray(image).astype(int) + brightness, 0, 255).astype(np.uint8))


def put(root: Path, split: str, label: str, name: str, image: Image.Image) -> None:
    folder = root / split / label
    folder.mkdir(parents=True, exist_ok=True)
    image.save(folder / name, quality=95)


def taxonomy(**overrides) -> Taxonomy:
    spec = {
        "seed": 7,
        "near_duplicate_distance": 12,
        "min_unique_images": 6,
        "min_eval_images": 1,
        "fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
        "classes": {
            "cotton_aphid": {"crop": "Cotton", "category": "pest", "sources": ["Cotton_Aphid"]},
            "cotton_bollworm": {
                "crop": "Cotton", "category": "pest", "sources": ["American_Bollworm", "bollworm"],
            },
        },
    }
    spec.update(overrides)
    return Taxonomy.from_dict(spec)


def fill(root: Path, label: str, first_seed: int, count: int, split: str = "Train") -> None:
    for i in range(count):
        put(root, split, label, f"img_{first_seed + i}.jpg", textured(first_seed + i))


def by_path(rows):
    return {row.path: row for row in rows}


def test_an_image_copied_into_the_test_folder_is_one_image_in_one_split(tmp_path):
    fill(tmp_path, "Cotton_Aphid", 0, 10)
    fill(tmp_path, "American_Bollworm", 100, 10)
    put(tmp_path, "Validation", "Cotton_Aphid", "copy.jpg", Image.open(tmp_path / "Train/Cotton_Aphid/img_0.jpg"))

    rows = by_path(build_manifest(tmp_path, taxonomy()))

    original, copy = rows["Train/Cotton_Aphid/img_0.jpg"], rows["Validation/Cotton_Aphid/copy.jpg"]
    assert original.group == copy.group
    assert {original.status, copy.status} == {"kept", "duplicate"}
    assert copy.split == original.split


def test_a_brightened_copy_is_a_near_duplicate_but_a_different_picture_is_not(tmp_path):
    fill(tmp_path, "Cotton_Aphid", 0, 10)
    put(tmp_path, "Train", "Cotton_Aphid", "bright.jpg", textured(0, brightness=12))

    rows = by_path(build_manifest(tmp_path, taxonomy()))

    assert rows["Train/Cotton_Aphid/bright.jpg"].group == rows["Train/Cotton_Aphid/img_0.jpg"].group
    assert rows["Train/Cotton_Aphid/img_1.jpg"].group != rows["Train/Cotton_Aphid/img_0.jpg"].group


def test_folders_the_taxonomy_merges_become_one_class(tmp_path):
    fill(tmp_path, "American_Bollworm", 0, 4)
    fill(tmp_path, "bollworm", 50, 4)

    rows = build_manifest(tmp_path, taxonomy())

    assert {row.label for row in rows} == {"cotton_bollworm"}
    assert all(row.status == "kept" for row in rows)


def test_the_same_picture_under_two_classes_is_left_out(tmp_path):
    fill(tmp_path, "Cotton_Aphid", 0, 10)
    fill(tmp_path, "American_Bollworm", 100, 10)
    put(tmp_path, "Train", "American_Bollworm", "mislabelled.jpg", textured(3))

    rows = by_path(build_manifest(tmp_path, taxonomy()))

    for path in ("Train/Cotton_Aphid/img_3.jpg", "Train/American_Bollworm/mislabelled.jpg"):
        assert rows[path].status == "conflict"
        assert rows[path].split == ""


def test_a_class_with_too_few_unique_images_is_dropped(tmp_path):
    fill(tmp_path, "Cotton_Aphid", 0, 10)
    fill(tmp_path, "American_Bollworm", 100, 5)

    rows = build_manifest(tmp_path, taxonomy())

    rare = [row for row in rows if row.label == "cotton_bollworm"]
    assert rare and all(row.status == "rare_class" and row.split == "" for row in rare)


def test_every_class_reaches_validation_and_test_and_mostly_trains(tmp_path):
    fill(tmp_path, "Cotton_Aphid", 0, 20)
    fill(tmp_path, "American_Bollworm", 100, 8)

    rows = [row for row in build_manifest(tmp_path, taxonomy()) if row.status == "kept"]

    for label in ("cotton_aphid", "cotton_bollworm"):
        splits = [row.split for row in rows if row.label == label]
        assert splits.count("val") >= 1 and splits.count("test") >= 1
        assert splits.count("train") > len(splits) / 2
    aphid = [row.split for row in rows if row.label == "cotton_aphid"]
    assert (aphid.count("train"), aphid.count("val"), aphid.count("test")) == (14, 3, 3)


def test_a_folder_the_taxonomy_does_not_know_is_an_error(tmp_path):
    fill(tmp_path, "Mystery_Pest", 0, 2)
    with pytest.raises(ValueError, match="Mystery_Pest"):
        build_manifest(tmp_path, taxonomy())


def test_building_twice_gives_the_same_file(tmp_path):
    data = tmp_path / "data"
    fill(data, "Cotton_Aphid", 0, 12)
    fill(data, "American_Bollworm", 100, 9, split="Validation")

    write_manifest(build_manifest(data, taxonomy()), tmp_path / "a.csv")
    write_manifest(build_manifest(data, taxonomy()), tmp_path / "b.csv")

    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()


def test_the_project_taxonomy_maps_every_dataset_folder_once():
    tax = Taxonomy.load(PROJECT / "taxonomy.yaml")
    sources = [source for spec in tax.classes.values() for source in spec.sources]
    assert len(sources) == len(set(sources)) == 40
    assert {spec.category for spec in tax.classes.values()} <= {"disease", "pest", "healthy"}

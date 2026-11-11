"""Build the photo check's evaluation set (#93): the manifest in git, the photos beside it out of git.

    uv run --with pyarrow python backend/scripts/build_photo_check_set.py

Needs the crop disease photos (`CSA_CROP_DATA_DIR`, the `dataset_filtered` folder) and two public sets, which it
downloads once into `backend/evaluations/photo_check/_downloads/`:

- other plants: PlantVillage's test split (BrandonFors/Plant-Diseases-PlantVillage-Dataset), maize left out;
- not plants: Imagenette (johnowhitaker/imagenette2-320), ten kinds of object and animal.

Every choice is drawn with a fixed seed. `tune` photos are for working on the prompt; `final` photos are scored
once it is frozen, and their five-crop photos come from the crop disease model's locked test split.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import random
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from csa_portal.ai.evals.photo_check import EVALUATION_DIR, Case, save_cases  # noqa: E402

CROP_MANIFEST = BACKEND.parent / "ml" / "crop-disease" / "data" / "manifest.csv"
DEFAULT_CROP_DATA = BACKEND.parent / "Aamir Ai  Project" / "Crop Disease Detection" / "dataset_filtered"
IMAGES = EVALUATION_DIR / "images"
DOWNLOADS = EVALUATION_DIR / "_downloads"
HUB = "https://huggingface.co/datasets"
SOURCES = {
    "plantvillage-test.parquet": f"{HUB}/BrandonFors/Plant-Diseases-PlantVillage-Dataset/resolve/main/data/test-00000-of-00001.parquet",
    "imagenette-train.parquet": f"{HUB}/johnowhitaker/imagenette2-320/resolve/main/data/train-00000-of-00001.parquet",
}
SEED = 93
PER_CROP = 100          # five-crop photos per crop, in each part
POOR_PER_CROP = 20      # degraded photos per crop, over both parts
OTHER_PLANTS = 200      # over both parts
NOT_PLANTS = 100        # over both parts
PARTS = ("tune", "final")


def crop_rows() -> dict[str, list[dict[str, str]]]:
    with CROP_MANIFEST.open(encoding="utf-8", newline="") as file:
        rows = [row for row in csv.DictReader(file) if row["status"] == "kept"]
    by_split: dict[str, list[dict[str, str]]] = {"val": [], "test": []}
    for row in rows:
        if row["split"] in by_split:
            by_split[row["split"]].append(row)
    return by_split


def five_crop_cases(by_split: dict[str, list[dict[str, str]]]) -> tuple[list[Case], list[dict[str, str]]]:
    """The clean five-crop photos for both parts, and the val rows left over for degrading."""
    cases: list[Case] = []
    spare: list[dict[str, str]] = []
    for part, split in (("tune", "val"), ("final", "test")):
        for crop in sorted({row["crop"] for row in by_split[split]}):
            rows = sorted((row for row in by_split[split] if row["crop"] == crop), key=lambda row: row["path"])
            random.Random(f"{SEED}-{split}-{crop}").shuffle(rows)
            cases += [Case(row["sha256"], part, "crop", crop, row["label"], split, row["path"]) for row in rows[:PER_CROP]]
            if split == "val":
                spare += rows[PER_CROP:PER_CROP + POOR_PER_CROP]
    return cases, spare


def degrade(image: Image.Image, how: str) -> Image.Image:
    image = image.convert("RGB")
    if how == "blurred":
        return image.filter(ImageFilter.GaussianBlur(max(image.size) / 60))
    if how == "dark":
        return ImageEnhance.Brightness(image).enhance(0.12)
    small = image.resize((max(1, image.width // 12), max(1, image.height // 12)))
    return small.resize(image.size)  # "coarse": the detail a far-off or tiny photo has lost


def poor_cases(spare: list[dict[str, str]], crop_data: Path) -> list[Case]:
    folder = IMAGES / "poor"
    folder.mkdir(parents=True, exist_ok=True)
    cases = []
    for number, row in enumerate(sorted(spare, key=lambda row: row["sha256"])):
        how = ("blurred", "dark", "coarse")[number % 3]
        with Image.open(crop_data / row["path"]) as image:
            buffer = io.BytesIO()
            degrade(image, how).save(buffer, "JPEG", quality=85)
        content = buffer.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        (folder / f"{digest}.jpg").write_bytes(content)
        cases.append(Case(digest, PARTS[number % 2], "poor", row["crop"], how, f"val:{row['path']}", f"poor/{digest}.jpg"))
    return cases


def download(name: str) -> Path:
    path = DOWNLOADS / name
    if not path.is_file():
        DOWNLOADS.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {name}")
        urllib.request.urlretrieve(SOURCES[name], path)  # noqa: S310 - a fixed https address
    return path


def public_cases(name: str, group: str, count: int, keep) -> list[Case]:
    """`count` photos drawn from a public parquet set, written out under the evaluation's image folder."""
    import pyarrow.parquet as pq

    file = pq.ParquetFile(download(name))
    meta = json.loads((file.schema_arrow.metadata or {}).get(b"huggingface", b"{}"))
    names = meta.get("info", {}).get("features", {}).get("label", {}).get("names")
    labels = file.read(columns=["label"]).column("label").to_pylist()
    wanted = [index for index, label in enumerate(labels) if keep(names[label] if names else str(label))]
    random.Random(f"{SEED}-{name}").shuffle(wanted)
    chosen = sorted(wanted[:count])
    images = file.read(columns=["image"]).column("image").take(chosen).to_pylist()
    folder = IMAGES / group
    folder.mkdir(parents=True, exist_ok=True)
    cases = []
    for number, (index, image) in enumerate(zip(chosen, images)):
        content = image["bytes"]
        digest = hashlib.sha256(content).hexdigest()
        with Image.open(io.BytesIO(content)) as opened:
            suffix = ".png" if opened.format == "PNG" else ".jpg"
        (folder / f"{digest}{suffix}").write_bytes(content)
        label = (names[labels[index]] if names else f"class {labels[index]}").split("___")[0].replace("_", " ").strip()
        cases.append(Case(digest, PARTS[number % 2], group, "", label, f"{name}:{index}", f"{group}/{digest}{suffix}"))
    return cases


def main() -> None:
    crop_data = Path(os.environ.get("CSA_CROP_DATA_DIR", DEFAULT_CROP_DATA))
    if not crop_data.is_dir():
        sys.exit(f"The crop disease photos are not at {crop_data}; set CSA_CROP_DATA_DIR")
    clean, spare = five_crop_cases(crop_rows())
    cases = clean + poor_cases(spare, crop_data)
    cases += public_cases("plantvillage-test.parquet", "other-plant", OTHER_PLANTS, lambda name: not name.startswith("Corn"))
    cases += public_cases("imagenette-train.parquet", "not-plant", NOT_PLANTS, lambda name: True)
    seen: set[str] = set()
    unique = [case for case in cases if not (case.id in seen or seen.add(case.id))]
    save_cases(sorted(unique, key=lambda case: (case.part, case.group, case.crop, case.id)))
    for part in PARTS:
        counts = {group: sum(c.part == part and c.group == group for c in unique) for group in ("crop", "poor", "other-plant", "not-plant")}
        print(part, counts)


if __name__ == "__main__":
    main()

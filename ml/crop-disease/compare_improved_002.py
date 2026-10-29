"""Compare the new model with the portal's `improved-002` on rice and maize images neither trained on.

Both models learned from the same public rice and maize datasets, and the original files are not on
this PC, so images are matched by original filename. An image counts when it is in `improved-002`'s
strict test split, in our val or test split, has a non-generic filename, and both datasets give it the
same class. Scores cover the classes the two taxonomies share.

    uv run compare_improved_002.py --split test --predictions runs/final-seed44/test/predictions.csv \
        --holdout <improved-002 project>/experiments/improved_002_strict_cropaware/strict_holdout_evaluation/holdout_predictions.csv
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import re
from collections import defaultdict
from pathlib import Path

from crop_disease.evaluate import classification_metrics

PROJECT = Path(__file__).resolve().parent
PACKAGE = PROJECT.parents[1] / "backend" / "models" / "crop-classification" / "improved-002"

# Our class -> the improved-002 classes that mean the same thing.
SHARED_CLASSES = {
    "rice_bacterial_blight": {"RICE_DISEASE_001"},
    "rice_brown_spot": {"RICE_DISEASE_002"},
    "rice_blast": {"RICE_DISEASE_004", "RICE_DISEASE_005"},  # leaf and neck blast
    "rice_tungro": {"RICE_DISEASE_006"},
    "maize_common_rust": {"MAIZE_DISEASE_001"},
    "maize_gray_leaf_spot": {"MAIZE_DISEASE_003"},
    "maize_healthy": {"MAIZE_HEALTHY"},
    "maize_armyworm": {"MAIZE_PEST_002"},
    "maize_fall_armyworm": {"MAIZE_PEST_005"},
    "maize_stem_borer": {"MAIZE_PEST_004"},  # "corn borer (species unspecified)": an approximate match
}
OTHER = "(not a shared class)"


def original_name(path: str) -> str:
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return re.sub(r"^(20k_(train|validation|test)_|topagri_)", "", name)


def is_generic(name: str) -> bool:
    """Names like `00000000.jpg` or `1.jpg` recur across unrelated datasets."""
    return re.fullmatch(r"\d+\.\w+", name) is not None


def matched_images(manifest_rows, holdout_rows, split: str) -> dict[str, tuple[str, str]]:
    """Path -> (crop, our label) for images in both held-out sets with the same class on both sides."""
    theirs: dict[str, set[str]] = defaultdict(set)
    for row in holdout_rows:
        if row["split"] == "test":
            theirs[original_name(row["project_relative_path"])].add(row["canonical_class_id"])
    matches = {}
    for row in manifest_rows:
        name = original_name(row["path"])
        their_classes = theirs.get(name, set())
        if (
            row["split"] == split
            and row["status"] == "kept"
            and row["label"] in SHARED_CLASSES
            and not is_generic(name)
            and their_classes
            and their_classes <= SHARED_CLASSES[row["label"]]
        ):
            matches[row["path"]] = (row["crop"], row["label"])
    return matches


def to_shared(class_id: str) -> str:
    return next((ours for ours, ids in SHARED_CLASSES.items() if class_id in ids), OTHER)


def score(truth: dict[str, str], predicted: dict[str, str]) -> dict[str, object]:
    """Accuracy and macro F1 over the shared classes present in `truth`."""
    paths = sorted(truth)
    names = sorted({*truth.values(), *(predicted[path] for path in paths), OTHER})
    position = {name: index for index, name in enumerate(names)}
    result = classification_metrics(
        [position[truth[path]] for path in paths], [position[predicted[path]] for path in paths], names
    )
    present = {name: values for name, values in result.per_class.items() if values["support"]}
    return {
        "images": len(paths),
        "accuracy": result.accuracy,
        "macro_f1": sum(values["f1"] for values in present.values()) / len(present),
        "per_class": {name: (values["f1"], values["support"]) for name, values in present.items()},
    }


def load_predictor(package: Path):
    spec = importlib.util.spec_from_file_location("improved_002_inference", package / "portal_inference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AgriculturePortalPredictor(package)


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=("val", "test"), required=True)
    parser.add_argument("--predictions", type=Path, required=True, help="the new model's predictions.csv")
    parser.add_argument("--holdout", type=Path, required=True, help="improved-002 holdout_predictions.csv")
    parser.add_argument("--package", type=Path, default=PACKAGE)
    parser.add_argument("--data-dir", type=Path, default=os.environ.get("CSA_CROP_DATA_DIR"))
    parser.add_argument("--manifest", type=Path, default=PROJECT / "data" / "manifest.csv")
    args = parser.parse_args()
    if args.data_dir is None:
        parser.error("give --data-dir or set CSA_CROP_DATA_DIR")

    matches = matched_images(read_csv(args.manifest), read_csv(args.holdout), args.split)
    new = {row["path"]: row["predicted"] for row in read_csv(args.predictions)}
    predictor = load_predictor(args.package)
    old = {
        path: to_shared(predictor.predict(args.data_dir / path, crop, top_k=1)[0]["canonical_class_id"])
        for path, (crop, _) in matches.items()
    }
    for crop in ("Rice", "Maize", None):
        truth = {path: label for path, (image_crop, label) in matches.items() if crop in (None, image_crop)}
        results = {
            "improved-002": score(truth, old),
            "new model": score(truth, {path: new[path] if new[path] in SHARED_CLASSES else OTHER for path in truth}),
        }
        print(f"\n## {crop or 'Rice and maize'} ({len(truth)} images)")
        for name, result in results.items():
            print(f"{name:13} accuracy={result['accuracy']:.4f} macro_f1={result['macro_f1']:.4f}")
        for label in sorted(results["new model"]["per_class"]):
            old_f1, support = results["improved-002"]["per_class"][label]
            new_f1, _ = results["new model"]["per_class"][label]
            print(f"  {label:24} {support:4}  improved-002 {old_f1:.3f}  new {new_f1:.3f}")


if __name__ == "__main__":
    main()

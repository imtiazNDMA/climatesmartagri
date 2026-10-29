"""Build backend/crop_guidance.json from Dr. Aamir's treatment guide, word for word.

    uv run python backend/scripts/import_treatment_guide.py "Aamir Ai  Project/Crop Disease Detection/treatment_guide.py"

The guide's TREATMENTS dict is read as data (ast.literal_eval), never executed. Entries are keyed
by the five-crop model's class ids through the source folders in taxonomy.yaml; improved-002
classes that mean the same thing are listed as aliases. The file starts as "review-pending": the
portal shows symptoms and prevention, and holds back treatment steps until a reviewer is recorded.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY = ROOT / "ml" / "crop-disease" / "taxonomy.yaml"
OUTPUT = ROOT / "backend" / "crop_guidance.json"

# improved-002 classes with the same meaning as a five-crop class (see compare_improved_002.py).
ALIASES = {
    "rice_bacterial_blight": ["RICE_DISEASE_001"],
    "rice_brown_spot": ["RICE_DISEASE_002"],
    "rice_blast": ["RICE_DISEASE_004", "RICE_DISEASE_005"],
    "rice_tungro": ["RICE_DISEASE_006"],
    "maize_common_rust": ["MAIZE_DISEASE_001"],
    "maize_gray_leaf_spot": ["MAIZE_DISEASE_003"],
    "maize_healthy": ["MAIZE_HEALTHY"],
    "maize_armyworm": ["MAIZE_PEST_002"],
    "maize_fall_armyworm": ["MAIZE_PEST_005"],
}

# Prevention items that are themselves chemical measures: held back with the treatment steps.
CHEMICAL_PREVENTION = {
    "Use certified, fungicide-treated, disease-free seed.",
    "Consider an at-plant systemic insecticide seed treatment in fields with a history of heavy early thrips pressure.",
    "Use certified, fungicide-treated seed.",
}


def guide_key(name: str) -> str:
    """The guide's own key rule: lower case, letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def read_treatments(path: Path) -> dict[str, dict]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(target, "id", None) == "TREATMENTS" for target in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"no TREATMENTS dict in {path}")


def build(treatments: dict[str, dict], taxonomy: dict) -> dict[str, object]:
    classes = {}
    for class_id, spec in sorted(taxonomy["classes"].items()):
        entry = next((treatments[guide_key(source)] for source in spec["sources"] if guide_key(source) in treatments), None)
        if entry is None:
            continue
        classes[class_id] = {
            "aliases": ALIASES.get(class_id, []),
            "name": entry["name"],
            "type": entry["type"],
            "symptoms": entry["symptoms"],
            "treatment_steps": entry["steps"],
            "prevention": [item for item in entry["prevention"] if item not in CHEMICAL_PREVENTION],
            "chemical_prevention": [item for item in entry["prevention"] if item in CHEMICAL_PREVENTION],
        }
    return {
        "version": "draft-2026-10",
        "source": "Dr. Aamir's treatment guide (treatment_guide.py), copied word for word",
        "status": "review-pending",
        "reviewer": None,
        "reviewed_on": None,
        "note": "Treatment steps name pesticide classes; the portal shows them only once an agronomist has "
                "reviewed this file and checked chemical measures against what is registered in Pakistan (#15).",
        "classes": classes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("guide", type=Path)
    parser.add_argument("--taxonomy", type=Path, default=TAXONOMY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    taxonomy = yaml.safe_load(args.taxonomy.read_text(encoding="utf-8"))
    guidance = build(read_treatments(args.guide), taxonomy)
    args.output.write_text(json.dumps(guidance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    missing = sorted(set(taxonomy["classes"]) - set(guidance["classes"]))
    print(f"{len(guidance['classes'])} classes written to {args.output}; no entry: {missing or 'none'}")


if __name__ == "__main__":
    main()

"""Export a trained checkpoint as a portal runtime package, in the same layout as `improved-002`.

    uv run package_model.py checkpoints/autoresearch-seed44-best.pt ../../backend/models/crop-classification/five-crop-001

The package holds a TorchScript model that takes images and the crop the user chose, and returns
probabilities over the classes of that crop only, plus its label map and inference helper.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import torch
from torch import nn

from crop_disease.manifest import Taxonomy
from crop_disease.tracking import file_sha256

PROJECT = Path(__file__).resolve().parent
CROPS = ("Cotton", "Maize", "Rice", "Sugarcane", "Wheat")
RUNTIME = PROJECT / "crop_disease" / "portal_runtime"


class CropAwareModel(nn.Module):
    """Probabilities over the chosen crop's classes; every other class is zero."""

    def __init__(self, model: nn.Module, crop_mask: torch.Tensor) -> None:
        super().__init__()
        self.model = model
        self.register_buffer("crop_mask", crop_mask)

    def forward(self, images: torch.Tensor, crop_indices: torch.Tensor) -> torch.Tensor:
        logits = self.model(images)
        allowed = self.crop_mask[crop_indices]
        return logits.masked_fill(~allowed, float("-inf")).softmax(dim=1)


def display_name(label: str, crop: str) -> str:
    """`cotton_american_bollworm` -> `American bollworm (cotton)`."""
    words = label.removeprefix(crop.lower() + "_").replace("_", " ")
    return f"{words[0].upper()}{words[1:]} ({crop.lower()})"


def label_map(class_names: list[str], taxonomy: Taxonomy) -> dict[str, object]:
    classes = []
    for index, name in enumerate(class_names):
        entry = taxonomy.classes[name]
        classes.append({
            "label_index": index,
            "canonical_class_id": name,
            "canonical_class": display_name(name, entry.crop),
            "crop": entry.crop,
            "category": entry.category,
        })
    return {"num_classes": len(classes), "ordering_rule": "training class order", "classes": classes}


def crop_mask(classes: list[dict[str, object]]) -> torch.Tensor:
    return torch.tensor([[item["crop"] == crop for item in classes] for crop in CROPS], dtype=torch.bool)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--taxonomy", type=Path, default=PROJECT / "taxonomy.yaml")
    parser.add_argument("--registered", default="crop-disease v1 (alias candidate)")
    args = parser.parse_args()

    from autoresearch.train import build_model

    saved = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if saved.get("layout") != "backbone-head":
        raise SystemExit("package_model.py expects an autoresearch backbone-head checkpoint")
    labels = label_map(list(saved["class_names"]), Taxonomy.load(args.taxonomy))
    model = build_model(len(saved["class_names"]), saved["model_name"], pretrained=False)
    model.load_state_dict(saved["model_state"])
    wrapped = CropAwareModel(model, crop_mask(labels["classes"])).eval()

    size = saved["image_size"]
    images = torch.randn(2, 3, size, size)
    crop_indices = torch.tensor([0, 4])
    with torch.inference_mode():
        traced = torch.jit.trace(wrapped, (images, crop_indices))
        if not torch.allclose(traced(images, crop_indices), wrapped(images, crop_indices), atol=1e-5):
            raise SystemExit("the traced model disagrees with the original")

    args.output.mkdir(parents=True, exist_ok=True)
    traced.save(str(args.output / "model.ts"))
    (args.output / "label_map.json").write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(RUNTIME / "portal_inference.py", args.output / "portal_inference.py")
    config = {
        "package_version": args.output.name,
        "format": "TorchScript",
        "model_file": "model.ts",
        "registered_model": args.registered,
        "model": saved["model_name"],
        "checkpoint_sha256": file_sha256(args.checkpoint),
        "model_ts_sha256": file_sha256(args.output / "model.ts"),
        "checkpoint_epoch": saved["epoch"],
        "val_macro_f1": round(saved["val_macro_f1"], 4),
        "inputs": {
            "images": f"float32[N,3,{size},{size}], resized to {size}x{size}, ImageNet normalized",
            "crop_indices": "int64[N], " + ", ".join(f"{crop}={index}" for index, crop in enumerate(CROPS)),
        },
        "output": f"float32[N,{labels['num_classes']}] probabilities; other crops' classes are zero",
        "confidence_calibrated": False,
    }
    (args.output / "inference_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()

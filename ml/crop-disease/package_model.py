"""Export a trained checkpoint as a portal runtime package, in the same layout as `improved-002`.

    uv run package_model.py checkpoints/autoresearch-seed44-best.pt ../../backend/models/crop-classification/five-crop-001         --calibration runs/calibration/calibration.json --verify-split test

The package holds a TorchScript model that takes images and the crop the user chose, and returns
calibrated probabilities over the classes of that crop only, plus its label map and inference helper.
`--verify-split` checks that the package, through the portal's own preprocessing, gives the same
answers as the checkpoint through the training pipeline.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
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
    """Probabilities over the chosen crop's classes, softened by the calibration temperature."""

    def __init__(self, model: nn.Module, crop_mask: torch.Tensor, temperature: float = 1.0) -> None:
        super().__init__()
        self.model = model
        self.register_buffer("crop_mask", crop_mask)
        self.register_buffer("temperature", torch.tensor(temperature))

    def forward(self, images: torch.Tensor, crop_indices: torch.Tensor) -> torch.Tensor:
        logits = self.model(images) / self.temperature
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
    parser.add_argument("--calibration", type=Path, help="calibration.json from calibrate.py")
    parser.add_argument("--verify-split", choices=("val", "test"))
    parser.add_argument("--data-dir", type=Path, default=os.environ.get("CSA_CROP_DATA_DIR"))
    parser.add_argument("--manifest", type=Path, default=PROJECT / "data" / "manifest.csv")
    args = parser.parse_args()
    calibration = json.loads(args.calibration.read_text(encoding="utf-8")) if args.calibration else None
    temperature = calibration["temperature"] if calibration else 1.0

    from autoresearch.train import build_model

    saved = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if saved.get("layout") != "backbone-head":
        raise SystemExit("package_model.py expects an autoresearch backbone-head checkpoint")
    labels = label_map(list(saved["class_names"]), Taxonomy.load(args.taxonomy))
    model = build_model(len(saved["class_names"]), saved["model_name"], pretrained=False)
    model.load_state_dict(saved["model_state"])
    wrapped = CropAwareModel(model, crop_mask(labels["classes"]), temperature).eval()

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
        "confidence_calibrated": calibration is not None,
    }
    if calibration:
        config.update({
            "temperature": round(temperature, 4),
            "review_threshold": calibration["review_threshold"],
            "calibration": {
                "fitted_on": "val",
                "val_ece_before": round(calibration["val_before"]["ece"], 4),
                "val_ece_after": round(calibration["val_after"]["ece"], 4),
                "target_accuracy_above_threshold": calibration["target_accuracy"],
                "val_coverage_above_threshold": round(calibration["threshold_on_val"]["coverage"], 4),
            },
        })
    (args.output / "inference_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    if args.verify_split:
        if args.data_dir is None:
            parser.error("--verify-split needs --data-dir or CSA_CROP_DATA_DIR")
        verify(wrapped, labels, args.output, args.data_dir, args.manifest, args.verify_split, size)


def verify(wrapped: CropAwareModel, labels, package: Path, data_dir: Path, manifest: Path, split: str, size: int) -> None:
    """Package through the portal's preprocessing vs the checkpoint through training's: same answers."""
    from PIL import Image
    from torchvision import transforms

    from crop_disease.dataset import read_dataset_index

    spec = importlib.util.spec_from_file_location("package_inference", package / "portal_inference.py")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    packaged = torch.jit.load(str(package / "model.ts"), map_location="cpu").eval()
    transform = transforms.Compose([
        transforms.Resize((size, size)), transforms.ToTensor(),
        transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
    ])
    crop_of = {item["label_index"]: item["crop"] for item in labels["classes"]}
    largest_gap, disagreements = 0.0, 0
    items = read_dataset_index(manifest, split).items
    with torch.inference_mode():
        for item in items:
            crop = torch.tensor([runtime.CROP_TO_INDEX[crop_of[item.target]]])
            with Image.open(data_dir / item.path) as source:
                reference = wrapped(transform(source.convert("RGB")).unsqueeze(0), crop)[0]
            portal = packaged(runtime.prepare_image(data_dir / item.path), crop)[0]
            largest_gap = max(largest_gap, float((reference - portal).abs().max()))
            disagreements += int(reference.argmax() != portal.argmax())
    print(f"verify {split}: {len(items)} images, top-1 disagreements {disagreements}, largest probability gap {largest_gap:.2e}")
    if disagreements or largest_gap > 1e-4:
        raise SystemExit("the package does not match the checkpoint within 1e-4")


if __name__ == "__main__":
    main()

"""Inference helper for the five-crop portal package. Same contract as `improved-002`'s helper.

Preprocessing matches evaluation in training: RGB, stretched to 224x224 with bilinear resampling,
ImageNet normalisation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image


TARGET_SIZE = (224, 224)
IMAGENET_MEAN = np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
IMAGENET_STD = np.asarray((0.229, 0.224, 0.225), dtype=np.float32)
CROP_TO_INDEX = {"Cotton": 0, "Maize": 1, "Rice": 2, "Sugarcane": 3, "Wheat": 4}


def prepare_image(path) -> torch.Tensor:
    with Image.open(path) as source:
        image = source.convert("RGB").resize(TARGET_SIZE, Image.Resampling.BILINEAR)
    array = np.asarray(image, dtype=np.float32) / 255.0
    array = (array - IMAGENET_MEAN) / IMAGENET_STD
    return torch.from_numpy(array.transpose(2, 0, 1)).unsqueeze(0)


class AgriculturePortalPredictor:
    def __init__(self, package_dir: str | Path) -> None:
        self.package_dir = Path(package_dir)
        self.model = torch.jit.load(str(self.package_dir / "model.ts"), map_location="cpu")
        self.model.eval()
        label_map = json.loads((self.package_dir / "label_map.json").read_text(encoding="utf-8"))
        self.labels = {int(item["label_index"]): item for item in label_map["classes"]}

    def predict(self, image_path, crop: str, top_k: int = 5) -> list[dict[str, object]]:
        if crop not in CROP_TO_INDEX:
            raise ValueError(f"crop must be one of {sorted(CROP_TO_INDEX)}")
        image = prepare_image(image_path)
        crop_index = torch.tensor([CROP_TO_INDEX[crop]], dtype=torch.long)
        with torch.inference_mode():
            probabilities = self.model(image, crop_index)[0]
        crop_classes = sum(1 for item in self.labels.values() if item["crop"] == crop)
        values, indices = probabilities.topk(min(top_k, crop_classes))
        return [
            {
                "label_index": int(label_index),
                "canonical_class_id": self.labels[int(label_index)]["canonical_class_id"],
                "canonical_class": self.labels[int(label_index)]["canonical_class"],
                "crop": self.labels[int(label_index)]["crop"],
                "category": self.labels[int(label_index)]["category"],
                "confidence": float(confidence),
            }
            for confidence, label_index in zip(values.tolist(), indices.tolist())
        ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--crop", required=True, choices=sorted(CROP_TO_INDEX))
    parser.add_argument("--package-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    predictor = AgriculturePortalPredictor(args.package_dir)
    print(json.dumps(predictor.predict(args.image, args.crop, args.top_k), indent=2))


if __name__ == "__main__":
    main()

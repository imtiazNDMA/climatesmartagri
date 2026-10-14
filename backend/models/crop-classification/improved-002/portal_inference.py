"""Standalone inference helper for the Agriculture Portal model package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image


TARGET_SIZE = (224, 224)
PAD_COLOR = (128, 128, 128)
IMAGENET_MEAN = np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
IMAGENET_STD = np.asarray((0.229, 0.224, 0.225), dtype=np.float32)
CROP_TO_INDEX = {"Rice": 0, "Maize": 1}


def prepare_image(path: str | Path) -> torch.Tensor:
    with Image.open(path) as source:
        if "A" in source.mode:
            background = Image.new("RGB", source.size, (255, 255, 255))
            rgba = source.convert("RGBA")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        else:
            image = source.convert("RGB")
        width, height = image.size
        scale = min(TARGET_SIZE[0] / width, TARGET_SIZE[1] / height)
        resized_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        resized = image.resize(resized_size, Image.Resampling.BICUBIC)
        canvas = Image.new("RGB", TARGET_SIZE, PAD_COLOR)
        offset = (
            (TARGET_SIZE[0] - resized_size[0]) // 2,
            (TARGET_SIZE[1] - resized_size[1]) // 2,
        )
        canvas.paste(resized, offset)

    array = np.asarray(canvas, dtype=np.float32) / 255.0
    array = (array - IMAGENET_MEAN) / IMAGENET_STD
    return torch.from_numpy(array.transpose(2, 0, 1)).unsqueeze(0)


class AgriculturePortalPredictor:
    def __init__(self, package_dir: str | Path) -> None:
        self.package_dir = Path(package_dir)
        self.model = torch.jit.load(str(self.package_dir / "model.ts"), map_location="cpu")
        self.model.eval()
        label_map = json.loads(
            (self.package_dir / "label_map.json").read_text(encoding="utf-8")
        )
        self.labels = {
            int(item["label_index"]): item for item in label_map["classes"]
        }

    def predict(
        self,
        image_path: str | Path,
        crop: str,
        top_k: int = 5,
    ) -> list[dict[str, object]]:
        if crop not in CROP_TO_INDEX:
            raise ValueError(f"crop must be one of {sorted(CROP_TO_INDEX)}")
        image = prepare_image(image_path)
        crop_index = torch.tensor([CROP_TO_INDEX[crop]], dtype=torch.long)
        with torch.inference_mode():
            probabilities = self.model(image, crop_index)[0]
        values, indices = probabilities.topk(min(top_k, len(self.labels)))
        results = []
        for confidence, label_index in zip(values.tolist(), indices.tolist()):
            label = self.labels[int(label_index)]
            results.append(
                {
                    "label_index": int(label_index),
                    "canonical_class_id": label["canonical_class_id"],
                    "canonical_class": label["canonical_class"],
                    "crop": label["crop"],
                    "category": label["category"],
                    "confidence": float(confidence),
                }
            )
        return results


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

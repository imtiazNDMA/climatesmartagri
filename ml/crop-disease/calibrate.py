"""Calibrate a checkpoint's confidence on the val split and choose the portal's expert-review threshold.

    uv run calibrate.py checkpoints/autoresearch-seed44-best.pt --run-id <mlflow run>

The portal tells the model which crop is in the picture, so calibration works on the same
crop-masked scores the package returns. Temperature scaling and the threshold are fitted on val
only; `--report-test` adds the test split as a held-out check, never used to choose anything.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from torchvision import transforms

from crop_disease.dataset import ManifestDataset, read_dataset_index
from crop_disease.manifest import Taxonomy

PROJECT = Path(__file__).resolve().parent
OUTPUT = PROJECT / "runs" / "calibration"
BINS = 15


def expected_calibration_error(confidence: np.ndarray, correct: np.ndarray, bins: int = BINS) -> float:
    """Gap between confidence and accuracy, averaged over equal-width confidence bins."""
    edges = np.linspace(0, 1, bins + 1)
    error = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        inside = (confidence > low) & (confidence <= high)
        if inside.any():
            error += inside.mean() * abs(confidence[inside].mean() - correct[inside].mean())
    return float(error)


def fit_temperature(logits: torch.Tensor, targets: torch.Tensor) -> float:
    """The temperature that minimises negative log-likelihood (Guo et al., 2017)."""
    log_temperature = torch.zeros(1, requires_grad=True)
    optimizer = torch.optim.LBFGS([log_temperature], lr=0.1, max_iter=200)

    def closure():
        optimizer.zero_grad()
        loss = torch.nn.functional.cross_entropy(logits / log_temperature.exp(), targets)
        loss.backward()
        return loss

    optimizer.step(closure)
    temperature = float(log_temperature.detach().exp())
    if not np.isfinite(temperature):
        raise RuntimeError("temperature fit diverged")
    return temperature


def threshold_table(confidence: np.ndarray, correct: np.ndarray) -> list[dict[str, float]]:
    """For each candidate threshold: the share of answers at or above it, and their accuracy."""
    rows = []
    for threshold in np.round(np.arange(0.30, 0.96, 0.05), 2):
        accepted = confidence >= threshold
        rows.append({
            "threshold": float(threshold),
            "coverage": float(accepted.mean()),
            "accuracy_accepted": float(correct[accepted].mean()) if accepted.any() else 1.0,
        })
    return rows


def choose_threshold(table: list[dict[str, float]], target_accuracy: float) -> dict[str, float]:
    """The lowest threshold whose accepted answers reach the target accuracy."""
    for row in table:
        if row["accuracy_accepted"] >= target_accuracy:
            return row
    return table[-1]


def masked_logits(checkpoint: Path, data_dir: Path, manifest: Path, split: str, taxonomy: Taxonomy, device):
    from autoresearch.train import build_model

    saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
    class_names = list(saved["class_names"])
    crops = [taxonomy.classes[name].crop for name in class_names]
    model = build_model(len(class_names), saved["model_name"], pretrained=False)
    model.load_state_dict(saved["model_state"])
    model.to(device).eval()
    size = saved["image_size"]
    transform = transforms.Compose([
        transforms.Resize((size, size)), transforms.ToTensor(),
        transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
    ])
    index = read_dataset_index(manifest, split)
    loader = DataLoader(ManifestDataset(data_dir, index, transform), batch_size=64, num_workers=4)
    outputs, targets = [], []
    with torch.inference_mode():
        for images, batch_targets in loader:
            outputs.append(model(images.to(device)).float().cpu())
            targets.append(batch_targets)
    logits, targets = torch.cat(outputs), torch.cat(targets)
    # The portal supplies the crop, so only that crop's classes can be answered. A large finite
    # value rather than -inf keeps the temperature's gradient defined; the probabilities are the same.
    crop_of = np.array(crops)
    allowed = torch.from_numpy(crop_of[None, :] == crop_of[targets.numpy()][:, None])
    return logits.masked_fill(~allowed, -1e4), targets, [item.path for item in index.items]


def summarise(logits: torch.Tensor, targets: torch.Tensor, temperature: float) -> dict[str, float]:
    probabilities = (logits / temperature).softmax(dim=1)
    confidence, predicted = probabilities.max(dim=1)
    correct = (predicted == targets).numpy().astype(float)
    nll = torch.nn.functional.cross_entropy(logits / temperature, targets).item()
    return {
        "accuracy": float(correct.mean()),
        "ece": expected_calibration_error(confidence.numpy(), correct),
        "nll": nll,
        "mean_confidence": float(confidence.mean()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--data-dir", type=Path, default=os.environ.get("CSA_CROP_DATA_DIR"))
    parser.add_argument("--manifest", type=Path, default=PROJECT / "data" / "manifest.csv")
    parser.add_argument("--taxonomy", type=Path, default=PROJECT / "taxonomy.yaml")
    parser.add_argument("--target-accuracy", type=float, default=0.98,
                        help="accuracy that answers above the review threshold must reach on val")
    parser.add_argument("--report-test", action="store_true", help="also report calibration on the test split")
    parser.add_argument("--run-id", help="log the calibration to this MLflow run")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.data_dir is None:
        parser.error("give --data-dir or set CSA_CROP_DATA_DIR")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    taxonomy = Taxonomy.load(args.taxonomy)

    val_logits, val_targets, _ = masked_logits(args.checkpoint, args.data_dir, args.manifest, "val", taxonomy, device)
    temperature = fit_temperature(val_logits, val_targets)
    calibrated = (val_logits / temperature).softmax(dim=1)
    confidence, predicted = calibrated.max(dim=1)
    correct = (predicted == val_targets).numpy().astype(float)
    table = threshold_table(confidence.numpy(), correct)
    chosen = choose_threshold(table, args.target_accuracy)
    result = {
        "temperature": temperature,
        "target_accuracy": args.target_accuracy,
        "review_threshold": chosen["threshold"],
        "val_before": summarise(val_logits, val_targets, 1.0),
        "val_after": summarise(val_logits, val_targets, temperature),
        "threshold_on_val": chosen,
        "threshold_table_val": table,
    }
    if args.report_test:
        test_logits, test_targets, _ = masked_logits(args.checkpoint, args.data_dir, args.manifest, "test", taxonomy, device)
        result["test_before"] = summarise(test_logits, test_targets, 1.0)
        result["test_after"] = summarise(test_logits, test_targets, temperature)
        test_confidence, test_predicted = (test_logits / temperature).softmax(dim=1).max(dim=1)
        test_correct = (test_predicted == test_targets).numpy().astype(float)
        accepted = test_confidence.numpy() >= chosen["threshold"]
        result["threshold_on_test"] = {
            "coverage": float(accepted.mean()),
            "accuracy_accepted": float(test_correct[accepted].mean()),
        }

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "calibration.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.run_id:
        from crop_disease.tracking import configure_mlflow

        mlflow, _ = configure_mlflow(PROJECT, "autoresearch")
        with mlflow.start_run(run_id=args.run_id):
            mlflow.log_metrics({
                "calibration_temperature": temperature,
                "val_ece_before": result["val_before"]["ece"],
                "val_ece_after": result["val_after"]["ece"],
                "review_threshold": chosen["threshold"],
            })
            mlflow.log_artifact(str(args.output / "calibration.json"), artifact_path="calibration")
    print(json.dumps({key: value for key, value in result.items() if key != "threshold_table_val"}, indent=2))
    for row in table:
        print(f"threshold {row['threshold']:.2f}  coverage {row['coverage']:.3f}  accuracy {row['accuracy_accepted']:.4f}")


if __name__ == "__main__":
    main()

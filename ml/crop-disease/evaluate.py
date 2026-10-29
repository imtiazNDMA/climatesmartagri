"""Evaluate a saved PyTorch crop-disease checkpoint on a manifest split."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import timm
import torch
from torch.utils.data import DataLoader

from crop_disease.dataset import ManifestDataset, read_dataset_index
from crop_disease.evaluate import evaluate_torch, write_evaluation_artifacts
from crop_disease.tracking import configure_mlflow
from train import build_model, image_transforms

PROJECT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--data-dir", type=Path, default=os.environ.get("CSA_CROP_DATA_DIR"))
    parser.add_argument("--manifest", type=Path, default=PROJECT / "data" / "manifest.csv")
    parser.add_argument("--split", choices=("val", "test"), default="val")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--output", type=Path, default=PROJECT / "runs" / "evaluation")
    parser.add_argument("--experiment", choices=("baseline", "manual", "autoresearch"))
    parser.add_argument("--run-id", help="Attach metrics and artifacts to an existing MLflow run")
    args = parser.parse_args()
    if args.data_dir is None:
        parser.error("give --data-dir or set CSA_CROP_DATA_DIR")
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA was requested but is unavailable; pass --device cpu or install CUDA PyTorch")
    device = torch.device(args.device)
    saved = torch.load(args.checkpoint, map_location=device, weights_only=False)
    index = read_dataset_index(args.manifest, args.split)
    _, transform = image_transforms(saved["image_size"])
    loader = DataLoader(
        ManifestDataset(args.data_dir, index, transform), batch_size=args.batch_size,
        num_workers=args.workers, pin_memory=device.type == "cuda",
    )
    if saved.get("layout") == "backbone-head":
        from autoresearch.train import build_model as build_backbone_head
        model = build_backbone_head(len(saved["class_names"]), saved["model_name"], pretrained=False)
    else:
        model = build_model(saved["model_name"], len(saved["class_names"]), pretrained=False)
    model.load_state_dict(saved["model_state"])
    model.to(device)
    result, _, y_true, y_pred = evaluate_torch(model, loader, saved["class_names"], device)
    write_evaluation_artifacts(result, y_true, y_pred, saved["class_names"], args.output)
    if args.experiment or args.run_id:
        if not args.experiment:
            parser.error("--experiment is required with --run-id")
        mlflow, _ = configure_mlflow(PROJECT, args.experiment)
        with mlflow.start_run(run_id=args.run_id):
            mlflow.log_metrics({
                f"{args.split}_accuracy": result.accuracy,
                f"{args.split}_macro_f1": result.macro_f1,
            })
            mlflow.log_artifacts(str(args.output), artifact_path=args.split)
    print(f"accuracy={result.accuracy:.4f} macro_f1={result.macro_f1:.4f}")


if __name__ == "__main__":
    main()

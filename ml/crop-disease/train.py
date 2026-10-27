from __future__ import annotations

import argparse
import json
import os
import random
import re
from collections import Counter
from pathlib import Path

import numpy as np
import timm
import torch
from torch import nn
from torch.amp import GradScaler, autocast
from torch.utils.data import DataLoader
from torchvision import transforms

from crop_disease.dataset import ManifestDataset, read_dataset_index
from crop_disease.evaluate import evaluate_torch, write_evaluation_artifacts
from crop_disease.tracking import configure_mlflow, file_sha256, git_commit

PROJECT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the five-crop disease classifier on the locked manifest")
    parser.add_argument("--data-dir", type=Path, default=os.environ.get("CSA_CROP_DATA_DIR"))
    parser.add_argument("--manifest", type=Path, default=PROJECT / "data" / "manifest.csv")
    parser.add_argument("--experiment", choices=("baseline", "manual", "autoresearch"), default="manual")
    parser.add_argument("--run-name")
    parser.add_argument("--model", default="mobilenetv2_100")
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--head-epochs", type=int, default=15)
    parser.add_argument("--fine-tune-epochs", type=int, default=25)
    parser.add_argument("--head-lr", type=float, default=1e-3)
    parser.add_argument("--fine-tune-lr", type=float, default=1e-5)
    parser.add_argument("--fine-tune-layers", type=int, default=40)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    return parser.parse_args()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cudnn.benchmark = False


def image_transforms(image_size: int):
    normalize = transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225))
    train = transforms.Compose([
        transforms.RandomResizedCrop(image_size, scale=(0.75, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.15, contrast=0.15),
        transforms.ToTensor(),
        normalize,
    ])
    evaluate = transforms.Compose([transforms.Resize((image_size, image_size)), transforms.ToTensor(), normalize])
    return train, evaluate


def make_loader(data_dir, manifest, split, transform, batch_size, workers, seed, shuffle=False):
    index = read_dataset_index(manifest, split)
    generator = torch.Generator().manual_seed(seed)
    dataset = ManifestDataset(data_dir, index, transform)
    return index, DataLoader(
        dataset, batch_size=batch_size, shuffle=shuffle, num_workers=workers,
        pin_memory=True, generator=generator, persistent_workers=workers > 0,
    )


def set_backbone_trainable(model, trainable: bool, fine_tune_layers: int) -> None:
    for parameter in model.parameters():
        parameter.requires_grad = False
    if trainable:
        classifier_ids = {id(module) for module in model.get_classifier().modules()}
        backbone_modules = [
            module for module in model.modules()
            if module is not model
            and id(module) not in classifier_ids
            and next(module.parameters(recurse=False), None) is not None
        ]
        for module in backbone_modules[-fine_tune_layers:]:
            for parameter in module.parameters(recurse=False):
                parameter.requires_grad = True
    classifier = model.get_classifier()
    for parameter in classifier.parameters():
        parameter.requires_grad = True


def build_model(model_name: str, num_classes: int, pretrained: bool = True):
    model = timm.create_model(model_name, pretrained=pretrained, num_classes=0)
    feature_count = model.num_features
    model.classifier = nn.Sequential(
        nn.Linear(feature_count, 256),
        nn.ReLU(),
        nn.Dropout(0.4),
        nn.Linear(256, num_classes),
    )
    return model


def train_epoch(model, loader, optimizer, criterion, scaler, device) -> float:
    model.train()
    total_loss = 0.0
    for images, targets in loader:
        images, targets = images.to(device), targets.to(device)
        optimizer.zero_grad(set_to_none=True)
        with autocast(device_type=device.type, enabled=device.type == "cuda"):
            logits = model(images)
            loss = criterion(logits, targets)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        total_loss += loss.item() * targets.size(0)
    return total_loss / len(loader.dataset)


def main() -> None:
    args = parse_args()
    if args.data_dir is None:
        raise SystemExit("give --data-dir or set CSA_CROP_DATA_DIR")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but is unavailable; install a CUDA-enabled PyTorch build")
    seed_everything(args.seed)
    device = torch.device(args.device)
    train_transform, eval_transform = image_transforms(args.image_size)
    train_index, train_loader = make_loader(
        args.data_dir, args.manifest, "train", train_transform, args.batch_size, args.workers, args.seed, True
    )
    val_index, val_loader = make_loader(
        args.data_dir, args.manifest, "val", eval_transform, args.batch_size, args.workers, args.seed
    )
    if train_index.class_names != val_index.class_names:
        raise SystemExit("train and validation class order differs")
    class_names = train_index.class_names
    expected_classes = frozenset(class_names)
    for split, index in (("train", train_index), ("validation", val_index)):
        missing = expected_classes - index.present_classes
        if missing:
            raise SystemExit(f"{split} split is missing classes: {sorted(missing)}")
    counts = Counter(item.target for item in train_index.items)
    class_weights = torch.tensor(
        [len(train_index.items) / (len(class_names) * counts[index]) for index in range(len(class_names))],
        dtype=torch.float32, device=device,
    )
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    model = build_model(args.model, len(class_names)).to(device)
    scaler = GradScaler(device.type, enabled=device.type == "cuda")
    checkpoints = PROJECT / "checkpoints"
    checkpoints.mkdir(exist_ok=True)
    checkpoint_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", args.run_name or f"{args.model}-{args.experiment}").strip(".-")
    if not checkpoint_name:
        raise SystemExit("run name must contain at least one letter or number")
    checkpoint = checkpoints / f"{checkpoint_name}-best.pt"
    artifacts = PROJECT / "runs" / (args.run_name or args.experiment)
    artifacts.mkdir(parents=True, exist_ok=True)
    mlflow, tracking_uri = configure_mlflow(PROJECT, args.experiment)
    print(f"MLflow: {tracking_uri}")

    params = vars(args).copy()
    params.update({
        "data_dir": str(args.data_dir), "manifest": str(args.manifest),
        "manifest_sha256": file_sha256(args.manifest), "git_commit": git_commit(PROJECT),
        "num_classes": len(class_names), "class_names": json.dumps(class_names),
    })
    with mlflow.start_run(run_name=args.run_name):
        mlflow.log_params(params)
        best_f1 = -1.0
        epoch_number = 0
        phases = (
            ("head", args.head_epochs, args.head_lr, False),
            ("fine_tune", args.fine_tune_epochs, args.fine_tune_lr, True),
        )
        for phase, epochs, learning_rate, backbone_trainable in phases:
            set_backbone_trainable(model, backbone_trainable, args.fine_tune_layers)
            optimizer = torch.optim.Adam(
                (parameter for parameter in model.parameters() if parameter.requires_grad),
                lr=learning_rate, weight_decay=args.weight_decay,
            )
            for _ in range(epochs):
                train_loss = train_epoch(model, train_loader, optimizer, criterion, scaler, device)
                val, val_loss, y_true, y_pred = evaluate_torch(model, val_loader, class_names, device, criterion)
                mlflow.log_metrics({
                    "train_loss": train_loss, "val_loss": val_loss,
                    "val_accuracy": val.accuracy, "val_macro_f1": val.macro_f1,
                }, step=epoch_number)
                print(
                    f"epoch={epoch_number + 1} phase={phase} train_loss={train_loss:.4f} "
                    f"val_loss={val_loss:.4f} val_accuracy={val.accuracy:.4f} val_macro_f1={val.macro_f1:.4f}"
                )
                if val.macro_f1 > best_f1:
                    best_f1 = val.macro_f1
                    torch.save({
                        "model_state": model.state_dict(), "model_name": args.model,
                        "class_names": class_names, "image_size": args.image_size,
                        "epoch": epoch_number, "val_macro_f1": best_f1,
                    }, checkpoint)
                    write_evaluation_artifacts(val, y_true, y_pred, class_names, artifacts / "val")
                epoch_number += 1
        mlflow.log_metric("best_val_macro_f1", best_f1)
        mlflow.log_artifact(str(checkpoint), artifact_path="model")
        mlflow.log_artifacts(str(artifacts / "val"), artifact_path="validation")
        model.load_state_dict(torch.load(checkpoint, map_location=device, weights_only=False)["model_state"])

if __name__ == "__main__":
    main()

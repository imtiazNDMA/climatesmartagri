"""Editable autoresearch candidate. This is the only Python file the research agent changes."""

from __future__ import annotations

import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import mlflow
import numpy as np
import timm
import torch
from torch import nn
from torch.amp import GradScaler, autocast
from torchvision import transforms

from autoresearch.prepare import TimeBudget, evaluate_macro_f1, load_data, make_loaders
from crop_disease.tracking import configure_mlflow, file_sha256, git_commit

DATA_DIR = Path(os.environ["CSA_CROP_DATA_DIR"])
MANIFEST = PROJECT / "data" / "manifest.csv"
SEED = 42
BATCH_SIZE = 128
WORKERS = 4
IMAGE_SIZE = 224
MODEL_NAME = "mobilenetv2_100"
HEAD_LR = 1e-3
FINE_TUNE_LR = 1e-5
HEAD_EPOCHS = 15
FINE_TUNE_LAYERS = 40


def seed_everything() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cudnn.benchmark = False


def build_model(num_classes: int):
    model = timm.create_model(MODEL_NAME, pretrained=True, num_classes=0)
    model.classifier = nn.Sequential(
        nn.Linear(model.num_features, 256), nn.ReLU(), nn.Dropout(0.4), nn.Linear(256, num_classes)
    )
    return model


def set_phase(model, fine_tune: bool) -> None:
    for parameter in model.parameters():
        parameter.requires_grad = False
    if fine_tune:
        classifier_ids = {id(module) for module in model.get_classifier().modules()}
        modules = [
            module for module in model.modules()
            if module is not model
            and id(module) not in classifier_ids
            and next(module.parameters(recurse=False), None) is not None
        ]
        for module in modules[-FINE_TUNE_LAYERS:]:
            for parameter in module.parameters(recurse=False):
                parameter.requires_grad = True
    for parameter in model.get_classifier().parameters():
        parameter.requires_grad = True


def train_epoch(model, loader, optimizer, criterion, scaler, device, budget: TimeBudget) -> float:
    model.train()
    total = 0.0
    seen = 0
    for images, targets in loader:
        if budget.expired():
            break
        images, targets = images.to(device), targets.to(device)
        optimizer.zero_grad(set_to_none=True)
        with autocast(device_type="cuda"):
            loss = criterion(model(images), targets)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        total += loss.item() * targets.size(0)
        seen += targets.size(0)
    return total / max(seen, 1)


def main() -> None:
    if not torch.cuda.is_available():
        raise SystemExit("autoresearch requires CUDA")
    seed_everything()
    device = torch.device("cuda")
    normalize = transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225))
    train_transform = transforms.Compose([
        transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.75, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.15, contrast=0.15),
        transforms.ToTensor(),
        normalize,
    ])
    val_transform = transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)), transforms.ToTensor(), normalize,
    ])
    prepared = load_data(DATA_DIR, MANIFEST)
    train_loader, val_loader = make_loaders(
        prepared, train_transform, val_transform, BATCH_SIZE, WORKERS, SEED
    )
    counts = Counter(item.target for item in prepared.train.items)
    weights = torch.tensor([
        len(prepared.train.items) / (len(prepared.train.class_names) * counts[index])
        for index in range(len(prepared.train.class_names))
    ], device=device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    model = build_model(len(prepared.train.class_names)).to(device)
    scaler = GradScaler("cuda")
    budget = TimeBudget.start()
    best_f1 = -1.0
    epoch = 0
    configure_mlflow(PROJECT, "autoresearch")
    description = os.environ.get("AUTORESEARCH_DESCRIPTION", "manual baseline pass")
    run_id = os.environ.get("MLFLOW_RUN_ID")
    with mlflow.start_run(run_id=run_id, run_name=None if run_id else description):
        mlflow.set_tags({"commit": git_commit(PROJECT), "description": description})
        mlflow.log_params({
            "model": MODEL_NAME, "image_size": IMAGE_SIZE, "batch_size": BATCH_SIZE,
            "head_lr": HEAD_LR, "fine_tune_lr": FINE_TUNE_LR,
            "manifest_sha256": file_sha256(MANIFEST), "seed": SEED,
            "class_names": json.dumps(prepared.train.class_names),
        })
        while not budget.expired():
            fine_tune = epoch >= HEAD_EPOCHS
            set_phase(model, fine_tune)
            optimizer = torch.optim.Adam(
                (parameter for parameter in model.parameters() if parameter.requires_grad),
                lr=FINE_TUNE_LR if fine_tune else HEAD_LR,
            )
            train_loss = train_epoch(model, train_loader, optimizer, criterion, scaler, device, budget)
            if budget.expired():
                break
            score = evaluate_macro_f1(model, val_loader, device)
            best_f1 = max(best_f1, score)
            mlflow.log_metrics({"train_loss": train_loss, "val_macro_f1": score}, step=epoch)
            epoch += 1
        peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)
        mlflow.log_metrics({"best_val_macro_f1": best_f1, "peak_vram_mb": peak_vram_mb})

    print(f"val_macro_f1: {best_f1:.6f}")
    print(f"peak_vram_mb: {peak_vram_mb:.1f}")


if __name__ == "__main__":
    main()

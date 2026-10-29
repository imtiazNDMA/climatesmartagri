"""Editable autoresearch candidate. This is the only Python file the research agent changes."""

from __future__ import annotations

import json
import math
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
from timm.utils import ModelEmaV3
import torch
from torch import nn
from torch.amp import GradScaler, autocast
from torchvision import transforms

from autoresearch.prepare import TimeBudget, evaluate_macro_f1, load_data, make_loaders
from crop_disease.tracking import configure_mlflow, file_sha256, git_commit

MANIFEST = PROJECT / "data" / "manifest.csv"
SEED = int(os.environ.get("CSA_SEED", "42"))
BATCH_SIZE = 128
WORKERS = 16
IMAGE_SIZE = 224
MODEL_NAME = "convnext_nano"
LR = 3e-4
WEIGHT_DECAY = 0.05
WARMUP_FRACTION = 0.03
SCHEDULE_FRACTION = 0.95
EMA_DECAY = 0.998


def seed_everything() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    torch.backends.cudnn.deterministic = False
    torch.backends.cudnn.benchmark = True


def build_model(num_classes: int, model_name: str = MODEL_NAME, pretrained: bool = True):
    backbone = timm.create_model(model_name, pretrained=pretrained, num_classes=0)
    head = nn.Sequential(
        nn.Linear(backbone.num_features, 256), nn.ReLU(), nn.Dropout(0.4), nn.Linear(256, num_classes)
    )
    return nn.Sequential(backbone, head)


def lr_at(budget: TimeBudget) -> float:
    progress = min(budget.elapsed() / (budget.seconds * SCHEDULE_FRACTION), 1.0)
    if progress < WARMUP_FRACTION:
        return LR * progress / WARMUP_FRACTION
    progress = (progress - WARMUP_FRACTION) / (1 - WARMUP_FRACTION)
    return LR * 0.5 * (1 + math.cos(math.pi * progress))


def train_epoch(model, ema, loader, optimizer, criterion, scaler, device, budget: TimeBudget) -> float:
    model.train()
    total = 0.0
    seen = 0
    for images, targets in loader:
        if budget.expired():
            break
        for group in optimizer.param_groups:
            group["lr"] = lr_at(budget)
        images, targets = images.to(device, non_blocking=True), targets.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with autocast(device_type="cuda"):
            loss = criterion(model(images), targets)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        ema.update(model)
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
    prepared = load_data(Path(os.environ["CSA_CROP_DATA_DIR"]), MANIFEST)
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
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scaler = GradScaler("cuda")
    ema = ModelEmaV3(model, decay=EMA_DECAY, use_warmup=True)
    checkpoints = PROJECT / "checkpoints"
    checkpoints.mkdir(exist_ok=True)
    checkpoint = checkpoints / f"autoresearch-seed{SEED}-best.pt"
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
            "lr": LR, "weight_decay": WEIGHT_DECAY,
            "manifest_sha256": file_sha256(MANIFEST), "seed": SEED,
            "class_names": json.dumps(prepared.train.class_names),
        })
        while not budget.expired():
            train_loss = train_epoch(model, ema, train_loader, optimizer, criterion, scaler, device, budget)
            if budget.expired():
                break
            score = evaluate_macro_f1(ema.module, val_loader, device)
            if score > best_f1:
                best_f1 = score
                torch.save({
                    "model_state": ema.module.state_dict(), "model_name": MODEL_NAME, "layout": "backbone-head",
                    "class_names": prepared.train.class_names, "image_size": IMAGE_SIZE,
                    "epoch": epoch, "val_macro_f1": best_f1, "seed": SEED,
                }, checkpoint)
            mlflow.log_metrics({"train_loss": train_loss, "val_macro_f1": score}, step=epoch)
            epoch += 1
        peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)
        mlflow.log_metrics({"best_val_macro_f1": best_f1, "peak_vram_mb": peak_vram_mb})
        if checkpoint.exists():
            mlflow.log_artifact(str(checkpoint), artifact_path="model")

    print(f"val_macro_f1: {best_f1:.6f}")
    print(f"peak_vram_mb: {peak_vram_mb:.1f}")


if __name__ == "__main__":
    main()

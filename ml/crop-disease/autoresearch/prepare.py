"""Fixed data and evaluation boundary for autoresearch.

This module deliberately has no split argument: autoresearch can load only train and validation.
The agent instructions in program.md prohibit editing this file.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from crop_disease.dataset import DatasetIndex, ManifestDataset, read_dataset_index
from crop_disease.evaluate import evaluate_torch

TRAINING_BUDGET_SECONDS = 10 * 60
KILL_AFTER_SECONDS = 20 * 60


@dataclass(frozen=True)
class PreparedData:
    data_dir: Path
    train: DatasetIndex
    val: DatasetIndex


@dataclass(frozen=True)
class TimeBudget:
    started_at: float
    seconds: float = TRAINING_BUDGET_SECONDS

    @classmethod
    def start(cls, seconds: float = TRAINING_BUDGET_SECONDS) -> "TimeBudget":
        return cls(time.monotonic(), seconds)

    def expired(self) -> bool:
        return time.monotonic() - self.started_at >= self.seconds

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at


def load_data(data_dir: Path, manifest: Path) -> PreparedData:
    return PreparedData(
        data_dir=Path(data_dir),
        train=read_dataset_index(manifest, "train"),
        val=read_dataset_index(manifest, "val"),
    )


def make_loaders(
    prepared: PreparedData,
    train_transform,
    val_transform,
    batch_size: int,
    workers: int,
    seed: int,
) -> tuple[DataLoader, DataLoader]:
    generator = torch.Generator().manual_seed(seed)
    train = DataLoader(
        ManifestDataset(prepared.data_dir, prepared.train, train_transform),
        batch_size=batch_size,
        shuffle=True,
        num_workers=workers,
        pin_memory=True,
        generator=generator,
        persistent_workers=workers > 0,
    )
    val = DataLoader(
        ManifestDataset(prepared.data_dir, prepared.val, val_transform),
        batch_size=batch_size,
        shuffle=False,
        num_workers=workers,
        pin_memory=True,
        persistent_workers=workers > 0,
    )
    return train, val


def evaluate_macro_f1(model, loader, device) -> float:
    result, _, _, _ = evaluate_torch(model, loader, loader.dataset.index.class_names, device)
    return result.macro_f1

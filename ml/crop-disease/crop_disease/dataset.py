from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from crop_disease.manifest import read_manifest


@dataclass(frozen=True)
class DatasetItem:
    path: str
    target: int


@dataclass(frozen=True)
class DatasetIndex:
    class_names: tuple[str, ...]
    items: tuple[DatasetItem, ...]
    present_classes: frozenset[str]


def read_dataset_index(manifest_path: Path, split: str) -> DatasetIndex:
    rows = read_manifest(manifest_path)
    class_names = tuple(sorted({row.label for row in rows if row.status == "kept"}))
    label_to_index = {label: index for index, label in enumerate(class_names)}
    items = tuple(
        DatasetItem(row.path, label_to_index[row.label])
        for row in rows
        if row.status == "kept" and row.split == split
    )
    if not items:
        raise ValueError(f"manifest contains no kept images for split {split!r}")
    return DatasetIndex(class_names, items, frozenset(row.label for row in rows if row.status == "kept" and row.split == split))


class ManifestDataset:
    def __init__(self, data_dir: Path, index: DatasetIndex, transform: Callable):
        self.data_dir = Path(data_dir)
        self.index = index
        self.transform = transform

    def __len__(self) -> int:
        return len(self.index.items)

    def __getitem__(self, position: int):
        item = self.index.items[position]
        with Image.open(self.data_dir / item.path) as source:
            image = source.convert("RGB")
            transformed = self.transform(image)
        return transformed, item.target

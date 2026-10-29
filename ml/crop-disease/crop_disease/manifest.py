"""A leak-free manifest of the crop disease images.

Every image gets a row: its hashes, its duplicate group, its cleaned class and the split it belongs to.
Copies of one picture (byte-identical, or alike enough to share a perceptual hash) form a group. A group
keeps one image and lands in exactly one split, so nothing seen in training is scored again. A group
whose copies carry different cleaned classes is left out, since its label cannot be trusted.

Usage: uv run python -m crop_disease.manifest --data-dir <dataset_filtered> [--out data/manifest.csv]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import random
from collections import Counter, defaultdict
from dataclasses import astuple, dataclass, fields
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

PROJECT = Path(__file__).resolve().parents[1]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLITS = ("train", "val", "test")


@dataclass(frozen=True)
class ClassSpec:
    crop: str
    category: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Taxonomy:
    seed: int
    near_duplicate_distance: int
    min_unique_images: int
    min_eval_images: int
    fractions: dict[str, float]
    classes: dict[str, ClassSpec]

    @classmethod
    def from_dict(cls, spec: dict) -> Taxonomy:
        classes = {
            name: ClassSpec(entry["crop"], entry["category"], tuple(entry["sources"]))
            for name, entry in spec["classes"].items()
        }
        return cls(
            seed=spec["seed"],
            near_duplicate_distance=spec["near_duplicate_distance"],
            min_unique_images=spec["min_unique_images"],
            min_eval_images=spec["min_eval_images"],
            fractions=dict(spec["fractions"]),
            classes=classes,
        )

    @classmethod
    def load(cls, path: Path) -> Taxonomy:
        return cls.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")))

    def class_of(self, source: str) -> str:
        for name, spec in self.classes.items():
            if source in spec.sources:
                return name
        raise ValueError(f"Folder {source!r} is not in the taxonomy")


@dataclass
class Row:
    path: str
    source_split: str
    source_label: str
    label: str
    crop: str
    category: str
    sha256: str
    dhash: str
    group: str
    status: str
    split: str


HASH_SIDE = 16


def image_hashes(path: Path) -> tuple[str, bytes]:
    """SHA-256 of the file, and a 256-bit difference hash of the picture.

    A 64-bit hash was too coarse here: distinct photographs sharing a layout, such as a leaf on a
    black background, came within a few bits of each other and chained into groups of hundreds.
    """
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    with Image.open(path) as image:
        image.draft("L", (128, 128))
        grey = np.asarray(image.convert("L").resize((HASH_SIDE + 1, HASH_SIDE), Image.BILINEAR), dtype=np.int16)
    return sha, np.packbits((grey[:, 1:] > grey[:, :-1]).flatten()).tobytes()


def _scan(data_dir: Path) -> list[tuple[str, str, str]]:
    found = []
    for split_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        for label_dir in sorted(p for p in split_dir.iterdir() if p.is_dir()):
            for file in sorted(label_dir.iterdir()):
                if file.suffix.lower() in IMAGE_EXTENSIONS:
                    found.append((file.relative_to(data_dir).as_posix(), split_dir.name, label_dir.name))
    return sorted(found)


def _groups(shas: list[str], dhashes: list[bytes], max_distance: int) -> list[int]:
    """Union-find over exact and near duplicates; returns each image's group root."""
    parent = list(range(len(shas)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    first: dict[str, int] = {}
    for i, sha in enumerate(shas):
        union(i, first.setdefault(sha, i))
    hashes = np.frombuffer(b"".join(dhashes), dtype=np.uint64).reshape(len(dhashes), -1)
    for start in range(0, len(hashes), 512):
        distance = np.bitwise_count(hashes[start:start + 512, None, :] ^ hashes[None, :, :]).sum(axis=2)
        for a, b in zip(*np.nonzero(distance <= max_distance)):
            if start + a < b:
                union(int(start + a), int(b))
    return [find(i) for i in range(len(shas))]


def _split_sizes(n: int, taxonomy: Taxonomy) -> tuple[int, int, int]:
    val = max(taxonomy.min_eval_images, round(n * taxonomy.fractions["val"]))
    test = max(taxonomy.min_eval_images, round(n * taxonomy.fractions["test"]))
    return n - val - test, val, test


def build_manifest(data_dir: Path, taxonomy: Taxonomy) -> list[Row]:
    found = _scan(Path(data_dir))
    labels = [taxonomy.class_of(source_label) for _, _, source_label in found]
    hashes = [image_hashes(Path(data_dir) / path) for path, _, _ in found]
    roots = _groups([sha for sha, _ in hashes], [dh for _, dh in hashes], taxonomy.near_duplicate_distance)

    group_names = {root: f"g{n:05d}" for n, root in enumerate(dict.fromkeys(roots))}
    members: dict[int, list[int]] = defaultdict(list)
    for i, root in enumerate(roots):
        members[root].append(i)

    status = ["duplicate"] * len(found)
    for root, idx in members.items():
        if len({labels[i] for i in idx}) > 1:
            for i in idx:
                status[i] = "conflict"
        else:
            status[idx[0]] = "kept"

    kept_per_class = Counter(labels[i] for i in range(len(found)) if status[i] == "kept")
    for i in range(len(found)):
        if status[i] != "conflict" and kept_per_class[labels[i]] < taxonomy.min_unique_images:
            status[i] = "rare_class"

    split_of_group: dict[int, str] = {}
    for label in sorted(kept_per_class):
        kept = [i for i in range(len(found)) if status[i] == "kept" and labels[i] == label]
        if not kept:
            continue
        random.Random(f"{taxonomy.seed}:{label}").shuffle(kept)
        n_train, n_val, _ = _split_sizes(len(kept), taxonomy)
        for position, i in enumerate(kept):
            split_of_group[roots[i]] = (
                "train" if position < n_train else "val" if position < n_train + n_val else "test"
            )

    rows = []
    for i, (path, source_split, source_label) in enumerate(found):
        spec = taxonomy.classes[labels[i]]
        rows.append(Row(
            path=path, source_split=source_split, source_label=source_label, label=labels[i],
            crop=spec.crop, category=spec.category, sha256=hashes[i][0], dhash=hashes[i][1].hex(),
            group=group_names[roots[i]], status=status[i],
            split=split_of_group.get(roots[i], "") if status[i] in ("kept", "duplicate") else "",
        ))
    return rows


def write_manifest(rows: list[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([field.name for field in fields(Row)])
        writer.writerows(astuple(row) for row in rows)


def read_manifest(path: Path) -> list[Row]:
    with open(path, newline="", encoding="utf-8") as file:
        return [Row(**record) for record in csv.DictReader(file)]


def write_report(rows: list[Row], taxonomy: Taxonomy, path: Path) -> None:
    status = Counter(row.status for row in rows)
    kept = [row for row in rows if row.status == "kept"]
    lines = [
        "# Crop disease dataset report",
        "",
        "Generated by `crop_disease.manifest` from `taxonomy.yaml`; do not edit by hand.",
        "",
        f"- Images scanned: {len(rows)}",
        f"- Unique images kept: {status['kept']}",
        f"- Duplicates folded into a kept image: {status['duplicate']}",
        f"- Left out, same picture under different classes: {status['conflict']}",
        f"- Left out, class below {taxonomy.min_unique_images} unique images: {status['rare_class']}",
        f"- Near-duplicate threshold: {taxonomy.near_duplicate_distance} bits of a {HASH_SIDE * HASH_SIDE}-bit difference hash",
        "",
        "| Class | Crop | Category | Folders | Train | Val | Test |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for name, spec in taxonomy.classes.items():
        counts = Counter(row.split for row in kept if row.label == name)
        folders = ", ".join(f"`{source}`" for source in spec.sources)
        if not counts:
            lines.append(f"| {name} (dropped) | {spec.crop} | {spec.category} | {folders} | – | – | – |")
            continue
        lines.append(
            f"| {name} | {spec.crop} | {spec.category} | {folders} "
            f"| {counts['train']} | {counts['val']} | {counts['test']} |"
        )
    totals = Counter(row.split for row in kept)
    lines.append(f"| **All** | | | | **{totals['train']}** | **{totals['val']}** | **{totals['test']}** |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=os.environ.get("CSA_CROP_DATA_DIR"))
    parser.add_argument("--taxonomy", type=Path, default=PROJECT / "taxonomy.yaml")
    parser.add_argument("--out", type=Path, default=PROJECT / "data" / "manifest.csv")
    parser.add_argument("--report", type=Path, default=PROJECT / "data" / "report.md")
    args = parser.parse_args()
    if args.data_dir is None:
        parser.error("give --data-dir or set CSA_CROP_DATA_DIR")
    taxonomy = Taxonomy.load(args.taxonomy)
    rows = build_manifest(args.data_dir, taxonomy)
    write_manifest(rows, args.out)
    write_report(rows, taxonomy, args.report)
    print(f"Wrote {args.out} and {args.report}: {Counter(row.status for row in rows)}")


if __name__ == "__main__":
    main()

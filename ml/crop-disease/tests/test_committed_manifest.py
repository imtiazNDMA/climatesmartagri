"""Checks on the committed manifest itself: these guard the real split, not the builder."""

from collections import defaultdict
from pathlib import Path

import numpy as np

from crop_disease.manifest import Taxonomy, read_manifest

PROJECT = Path(__file__).resolve().parents[1]
ROWS = read_manifest(PROJECT / "data" / "manifest.csv")
TAXONOMY = Taxonomy.load(PROJECT / "taxonomy.yaml")
IN_SPLITS = [row for row in ROWS if row.split]


def test_no_picture_is_in_more_than_one_split():
    for key in ("sha256", "group"):
        splits = defaultdict(set)
        for row in IN_SPLITS:
            splits[getattr(row, key)].add(row.split)
        assert all(len(found) == 1 for found in splits.values()), key


def test_no_evaluation_picture_is_a_near_copy_of_a_training_picture():
    def words(split_is_train: bool) -> np.ndarray:
        hashes = [bytes.fromhex(row.dhash) for row in IN_SPLITS if (row.split == "train") == split_is_train]
        assert all(len(h) == 32 for h in hashes), "difference hashes are 256 bits"
        return np.frombuffer(b"".join(hashes), dtype=np.uint64).reshape(-1, 4)

    train, held_out = words(True), words(False)
    for start in range(0, len(held_out), 512):
        block = held_out[start:start + 512, None, :] ^ train[None, :, :]
        assert np.bitwise_count(block).sum(axis=2).min() > TAXONOMY.near_duplicate_distance


def test_only_one_image_per_group_is_trained_or_scored():
    kept = defaultdict(int)
    for row in ROWS:
        kept[row.group] += row.status == "kept"
    assert max(kept.values()) == 1


def test_every_kept_class_is_scored_on_enough_images():
    for label in {row.label for row in ROWS if row.status == "kept"}:
        splits = [row.split for row in ROWS if row.status == "kept" and row.label == label]
        assert splits.count("val") >= TAXONOMY.min_eval_images, label
        assert splits.count("test") >= TAXONOMY.min_eval_images, label


def test_look_alike_pictures_do_not_chain_into_one_huge_group():
    # Pictures that merely share a layout (a leaf on black) must not link up into one group:
    # it would throw away hundreds of distinct photographs as "copies".
    sizes = defaultdict(int)
    for row in ROWS:
        sizes[row.group] += 1
    assert max(sizes.values()) <= 30

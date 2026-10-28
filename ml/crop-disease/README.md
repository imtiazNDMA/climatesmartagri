# Crop disease model

The pest and disease classifier for cotton, maize, rice, sugarcane and wheat, from data to experiments. The plan is tracked in #65.

## Data

The images (about 18,000 across 40 folders, 2.4 GB) stay outside git. Point `CSA_CROP_DATA_DIR` at the `dataset_filtered` folder, which holds `Train/` and `Validation/`, each with one folder per class.

What git holds:

- `taxonomy.yaml`: maps the 40 folders to cleaned classes, with each class's crop and its category (disease, pest or healthy).
- `data/manifest.csv`: one row per image, with its hashes, duplicate group, cleaned class, status and split. Training and evaluation read only this file.
- `data/report.md`: per-class counts, generated with the manifest.

Rebuilding gives a byte-identical manifest for the same images and taxonomy:

```sh
uv run python -m crop_disease.manifest --data-dir "$CSA_CROP_DATA_DIR"
```

### Why the split is rebuilt

In the original data, 57% of the `Validation` images were copies of `Train` images, and `Train` held many internal copies. Scores measured on it were inflated.

The manifest groups copies, so that no picture is ever both trained on and scored:

- byte-identical files (same SHA-256)
- near-identical pictures, within 12 bits of a 256-bit difference hash

Each group keeps one image and sits in exactly one split, chosen per class with a fixed seed: 70% train, 15% val, 15% test. A group whose copies carry different classes is left out, since its label can't be trusted. So is a class with fewer than 25 unique images.

The test split is locked. It is used only to score the final model; changing it means a new manifest version.

## Tests

```sh
uv run pytest
```

`tests/test_committed_manifest.py` checks the committed manifest itself:

- no picture appears in two splits
- no held-out picture is a near copy of a training picture
- every class has enough validation and test images
- no runaway duplicate groups

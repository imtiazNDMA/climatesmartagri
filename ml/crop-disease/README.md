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

## Training and experiment tracking

Training uses PyTorch, `timm`, the committed manifest, and the Windows CUDA build of PyTorch. Every run is written to a local SQLite-backed MLflow store under `.mlflow/`.

```powershell
$env:CSA_CROP_DATA_DIR = "G:\path\to\dataset_filtered"
uv run train.py --experiment baseline --run-name pytorch-mobilenetv2-baseline
```

The default baseline keeps the historical MobileNetV2 architecture and schedule: a 256-unit ReLU head with 0.4 dropout, 15 head-only epochs using Adam at `1e-3`, followed by 25 epochs fine-tuning the final 40 backbone modules at `1e-5`. It adds the issue's required class-balanced loss. Model selection uses validation macro F1. Training never reads the locked test split.

Open the experiment UI in another terminal:

```powershell
uv run mlflow ui --backend-store-uri sqlite:///.mlflow/mlflow.db --default-artifact-root .mlflow/artifacts
```

Runs log hyperparameters, git commit, manifest hash, per-epoch loss/accuracy/macro F1, the best checkpoint, a per-class JSON report, and a confusion matrix. Use `--experiment manual` for hand-tuned runs; `autoresearch` is reserved for #68.

Evaluate a saved PyTorch checkpoint without training:

```powershell
uv run evaluate.py checkpoints/pytorch-mobilenetv2-baseline-best.pt --split val
```

Only after selecting the final model configuration, evaluate the locked test split once with `--split test` and record that run alongside the model decision.

The historical Keras model is inference-only and isolated in an optional dependency group:

```powershell
uv sync --group keras
uv run --group keras baseline_keras.py path/to/best_model.keras path/to/class_names.json
```

## Autoresearch

The validation-only experiment loop lives in `autoresearch/`. Its fixed `prepare.py` exposes train and validation data only; `autoresearch/train.py` is the sole agent-editable file. Each run has a ten-minute training budget and a hard 20-minute subprocess timeout.

Read `autoresearch/program.md` before running an experiment. From this project directory, record one committed candidate with:

```powershell
uv run python -m autoresearch.run --commit <sha> --description "<idea>" --baseline 0.8304
```

Local `results.tsv`, `run.log`, checkpoints, and MLflow state remain outside git.

## Calibration and the portal package

Fit temperature scaling and the expert-review threshold on the val split, then export the portal package and check it against the checkpoint:

```powershell
uv run calibrate.py checkpoints/autoresearch-seed44-best.pt --report-test
uv run package_model.py checkpoints/autoresearch-seed44-best.pt ../../backend/models/crop-classification/five-crop-001 `
    --calibration runs/calibration/calibration.json --verify-split test
```

The review threshold is the lowest confidence at which accepted answers reach `--target-accuracy` (default 0.98) on val; the test split is only reported. `model.ts` is not in git, so a fresh checkout needs this step before the portal can classify cotton, wheat and sugarcane.

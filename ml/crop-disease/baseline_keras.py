"""Evaluate the historical 40-class Keras model on the clean manifest splits."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

from crop_disease.dataset import read_dataset_index
from crop_disease.evaluate import classification_metrics, write_evaluation_artifacts
from crop_disease.manifest import Taxonomy
from crop_disease.tracking import configure_mlflow, file_sha256, git_commit

PROJECT = Path(__file__).resolve().parent


def preprocess(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        return np.asarray(source.convert("RGB").resize((224, 224)), dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("class_names", type=Path)
    parser.add_argument("--data-dir", type=Path, default=os.environ.get("CSA_CROP_DATA_DIR"))
    parser.add_argument("--manifest", type=Path, default=PROJECT / "data" / "manifest.csv")
    parser.add_argument("--taxonomy", type=Path, default=PROJECT / "taxonomy.yaml")
    parser.add_argument("--split", choices=("val", "test"), action="append", default=[])
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--run-name", default="keras-historical-clean-split")
    args = parser.parse_args()
    if args.data_dir is None:
        parser.error("give --data-dir or set CSA_CROP_DATA_DIR")
    splits = args.split or ["val", "test"]

    try:
        import tensorflow as tf
    except ImportError as error:
        raise SystemExit("install TensorFlow for this inference-only baseline: uv add --optional keras tensorflow") from error

    source_names = json.loads(args.class_names.read_text(encoding="utf-8"))
    source_to_index = {name: index for index, name in enumerate(source_names)}
    taxonomy = Taxonomy.load(args.taxonomy)
    clean_names = read_dataset_index(args.manifest, "train").class_names
    source_groups = [
        [source_to_index[source] for source in taxonomy.classes[name].sources if source in source_to_index]
        for name in clean_names
    ]
    missing = [name for name, group in zip(clean_names, source_groups) if not group]
    if missing:
        raise SystemExit(f"historical model has no source output for cleaned classes: {missing}")
    model = tf.keras.models.load_model(args.model)
    mlflow, tracking_uri = configure_mlflow(PROJECT, "baseline")
    print(f"MLflow: {tracking_uri}")
    with mlflow.start_run(run_name=args.run_name):
        mlflow.log_params({
            "baseline": "keras_historical", "model": str(args.model),
            "model_sha256": file_sha256(args.model), "manifest_sha256": file_sha256(args.manifest),
            "git_commit": git_commit(PROJECT), "batch_size": args.batch_size,
        })
        for split in splits:
            index = read_dataset_index(args.manifest, split)
            y_true: list[int] = []
            y_pred: list[int] = []
            for start in range(0, len(index.items), args.batch_size):
                items = index.items[start:start + args.batch_size]
                batch = np.stack([preprocess(args.data_dir / item.path) for item in items])
                source_probabilities = model.predict(batch, verbose=0)
                clean_probabilities = np.stack([
                    source_probabilities[:, group].sum(axis=1) if group else np.zeros(len(items))
                    for group in source_groups
                ], axis=1)
                y_true.extend(item.target for item in items)
                y_pred.extend(clean_probabilities.argmax(axis=1).tolist())
            result = classification_metrics(y_true, y_pred, clean_names)
            output = PROJECT / "runs" / args.run_name / split
            write_evaluation_artifacts(result, y_true, y_pred, clean_names, output)
            mlflow.log_metrics({f"{split}_accuracy": result.accuracy, f"{split}_macro_f1": result.macro_f1})
            mlflow.log_artifacts(str(output), artifact_path=split)
            print(f"{split}_accuracy={result.accuracy:.4f} {split}_macro_f1={result.macro_f1:.4f}")


if __name__ == "__main__":
    main()

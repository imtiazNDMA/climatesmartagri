from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class EvaluationResult:
    accuracy: float
    macro_f1: float
    per_class: dict[str, dict[str, float | int]]

    def as_dict(self) -> dict[str, object]:
        return {
            "accuracy": self.accuracy,
            "macro_f1": self.macro_f1,
            "per_class": self.per_class,
        }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def classification_metrics(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    class_names: Sequence[str],
) -> EvaluationResult:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must contain the same number of items")
    if not y_true:
        raise ValueError("at least one prediction is required")

    per_class: dict[str, dict[str, float | int]] = {}
    f1_scores = []
    for index, name in enumerate(class_names):
        true_positive = sum(actual == predicted == index for actual, predicted in zip(y_true, y_pred))
        false_positive = sum(actual != index and predicted == index for actual, predicted in zip(y_true, y_pred))
        false_negative = sum(actual == index and predicted != index for actual, predicted in zip(y_true, y_pred))
        support = sum(actual == index for actual in y_true)
        precision = _ratio(true_positive, true_positive + false_positive)
        recall = _ratio(true_positive, true_positive + false_negative)
        f1 = _ratio(2 * precision * recall, precision + recall)
        f1_scores.append(f1)
        per_class[name] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

    return EvaluationResult(
        accuracy=sum(actual == predicted for actual, predicted in zip(y_true, y_pred)) / len(y_true),
        macro_f1=sum(f1_scores) / len(f1_scores),
        per_class=per_class,
    )


def evaluate_torch(model, loader, class_names: Sequence[str], device, criterion=None):
    import torch

    model.eval()
    y_true: list[int] = []
    y_pred: list[int] = []
    total_loss = 0.0
    with torch.inference_mode():
        for images, targets in loader:
            images, targets = images.to(device), targets.to(device)
            logits = model(images)
            if criterion is not None:
                total_loss += criterion(logits, targets).item() * targets.size(0)
            y_true.extend(targets.cpu().tolist())
            y_pred.extend(logits.argmax(dim=1).cpu().tolist())
    result = classification_metrics(y_true, y_pred, class_names)
    loss = total_loss / len(y_true) if criterion is not None else None
    return result, loss, y_true, y_pred


def write_evaluation_artifacts(
    result: EvaluationResult,
    y_true: Sequence[int],
    y_pred: Sequence[int],
    class_names: Sequence[str],
    output_dir: Path,
) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "classification_report.json"
    report_path.write_text(json.dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8")
    matrix = confusion_matrix(y_true, y_pred, labels=np.arange(len(class_names)))
    size = max(10, len(class_names) * 0.35)
    figure, axis = plt.subplots(figsize=(size, size))
    ConfusionMatrixDisplay(matrix, display_labels=class_names).plot(
        ax=axis, xticks_rotation=90, colorbar=False, values_format="d"
    )
    figure.tight_layout()
    matrix_path = output_dir / "confusion_matrix.png"
    figure.savefig(matrix_path, dpi=160)
    plt.close(figure)
    return report_path, matrix_path

import pytest

from crop_disease.evaluate import classification_metrics


def test_classification_metrics_report_accuracy_macro_f1_and_each_class():
    # Class 0: perfect, class 1: one miss, class 2: never predicted.
    result = classification_metrics(
        y_true=[0, 1, 1, 2],
        y_pred=[0, 1, 0, 1],
        class_names=["healthy", "rust", "blight"],
    )

    assert result.accuracy == pytest.approx(0.5)
    assert result.macro_f1 == pytest.approx((2 / 3 + 1 / 2 + 0) / 3)
    assert result.per_class["healthy"] == pytest.approx(
        {"precision": 0.5, "recall": 1.0, "f1": 2 / 3, "support": 1}
    )
    assert result.per_class["rust"] == pytest.approx(
        {"precision": 0.5, "recall": 0.5, "f1": 0.5, "support": 2}
    )
    assert result.per_class["blight"] == pytest.approx(
        {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 1}
    )

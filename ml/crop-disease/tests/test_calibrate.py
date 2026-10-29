import numpy as np
import pytest
import torch

from calibrate import choose_threshold, expected_calibration_error, fit_temperature, threshold_table


def test_calibration_error_is_zero_when_confidence_matches_accuracy():
    confidence = np.array([0.75, 0.75, 0.75, 0.75])
    correct = np.array([1.0, 1.0, 1.0, 0.0])

    assert expected_calibration_error(confidence, correct) == pytest.approx(0.0)


def test_calibration_error_measures_overconfidence():
    confidence = np.array([0.95, 0.95])
    correct = np.array([1.0, 0.0])

    assert expected_calibration_error(confidence, correct) == pytest.approx(0.45)


def test_temperature_softens_an_overconfident_model():
    torch.manual_seed(0)
    targets = torch.randint(0, 3, (400,))
    logits = torch.randn(400, 3)
    logits[torch.arange(400), targets] += 1.0
    overconfident = logits * 5

    assert fit_temperature(overconfident, targets) > 2.0


def test_temperature_fit_survives_classes_masked_out_for_the_crop():
    logits = torch.tensor([[2.0, 0.5, -1e4], [0.2, 1.5, -1e4]] * 50)
    targets = torch.tensor([0, 1] * 50)

    assert np.isfinite(fit_temperature(logits, targets))


def test_the_review_threshold_is_the_lowest_that_reaches_the_target_accuracy():
    confidence = np.array([0.32, 0.42, 0.62, 0.72, 0.92])
    correct = np.array([0.0, 1.0, 0.0, 1.0, 1.0])

    chosen = choose_threshold(threshold_table(confidence, correct), target_accuracy=0.99)

    assert chosen["threshold"] == pytest.approx(0.65)
    assert (chosen["coverage"], chosen["accuracy_accepted"]) == (pytest.approx(0.4), 1.0)

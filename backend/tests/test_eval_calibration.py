import math

from csa_portal.ai.evals.calibration import MIN_KAPPA, MIN_LABELS, calibration, cohens_kappa, confusion


def pairs(both, human_only, judge_only, neither):
    return [(True, True)] * both + [(True, False)] * human_only + [(False, True)] * judge_only + [(False, False)] * neither


def test_kappa_matches_the_textbook_example():
    # 50 answers: 20 both faithful, 5 human only, 10 judge only, 15 neither. Observed agreement 0.7, chance 0.5.
    assert math.isclose(cohens_kappa(pairs(20, 5, 10, 15)), 0.4)


def test_kappa_is_one_for_full_agreement_and_minus_one_for_full_disagreement():
    assert cohens_kappa(pairs(3, 0, 0, 2)) == 1.0
    assert cohens_kappa(pairs(0, 1, 1, 0)) == -1.0


def test_kappa_is_undefined_with_no_pairs_or_when_both_always_say_the_same():
    assert cohens_kappa([]) is None
    assert cohens_kappa(pairs(4, 0, 0, 0)) is None


def test_the_confusion_matrix_counts_each_kind_of_agreement():
    assert confusion(pairs(2, 1, 3, 4)) == {"both_faithful": 2, "human_only": 1, "judge_only": 3, "neither": 4}


def test_a_judge_is_calibrated_with_enough_labels_and_enough_agreement():
    assert (MIN_LABELS, MIN_KAPPA) == (20, 0.6)
    assert calibration(pairs(10, 0, 0, 9)).calibrated is False      # 19 labels
    assert calibration(pairs(10, 0, 0, 10)).calibrated is True      # 20 labels, kappa 1
    weak = calibration(pairs(8, 2, 4, 6))                           # 20 labels, kappa 0.4
    assert (weak.labels, weak.calibrated) == (20, False)
    assert math.isclose(weak.kappa, 0.4)
    assert calibration(pairs(20, 0, 0, 0)).calibrated is False      # kappa undefined

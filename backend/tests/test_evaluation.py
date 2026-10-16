from csa_portal.evaluation import score_grounding


def test_grounding_accepts_display_rounding_and_rejects_invented_numbers():
    assert score_grounding("The value is 30.9% from 12.78 million acres.", [30.87, 12.78]).passed
    result = score_grounding("The value is 31.8%.", [30.87])
    assert result.unsupported == (31.8,)


def test_grounding_does_not_read_digits_embedded_in_terms_as_figures():
    assert score_grounding("Carbon dioxide (CO2) is shown in the section.", []).numbers == ()

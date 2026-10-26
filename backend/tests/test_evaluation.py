from csa_portal.evaluation import score_grounding


def test_grounding_accepts_display_rounding_and_rejects_invented_numbers():
    assert score_grounding("The value is 30.9% from 12.78 million acres.", [30.87, 12.78]).passed
    result = score_grounding("The value is 31.8%.", [30.87])
    assert result.unsupported == (31.8,)


def test_grounding_does_not_read_digits_embedded_in_terms_as_figures():
    assert score_grounding("Carbon dioxide (CO2) is shown in the section.", []).numbers == ()


def test_list_numbering_at_the_start_of_a_line_is_not_a_figure():
    answer = "The portal can help with:\n1. Land classification for 29.29 million acres\n2) Irrigation\n(3) Crop calendars"

    assert score_grounding(answer, [29.29]).numbers == (29.29,)
    assert score_grounding("In 2026. supply was 92.79", []).numbers == (2026.0, 92.79)


def test_markdown_table_row_numbers_are_not_factual_figures():
    answer = """| # | Section | Status |
|---|---|---|
| 1 | Land Classification | Ready |
| 2 | Irrigation | Ready |
| 10 | Weather Forecast | Ready |"""

    assert score_grounding(answer, []).numbers == ()

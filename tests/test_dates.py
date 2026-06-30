from datetime import date

from opentrial.integrations._dates import safe_year


def test_safe_year_keeps_valid_years():
    assert safe_year(2020) == 2020
    assert safe_year("2019-03-01") == 2019


def test_safe_year_clamps_out_of_range_to_fallback():
    this_year = date.today().year
    assert safe_year(1887) == this_year          # pre-1900 reference
    assert safe_year("0019") == this_year        # garbled date artefact
    assert safe_year(this_year + 50) == this_year  # implausible future


def test_safe_year_handles_missing_or_unparseable():
    this_year = date.today().year
    assert safe_year(None) == this_year
    assert safe_year("not a year") == this_year


def test_safe_year_respects_explicit_fallback():
    assert safe_year(None, fallback=2000) == 2000

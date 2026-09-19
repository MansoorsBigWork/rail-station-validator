import pytest

from railvalidator.matcher import Verdict


def check(matcher, value):
    result = matcher.validate(value)
    return result.verdict, [c.name for c in result.candidates]


# -- one test per tier ------------------------------------------------------


def test_match_after_normalisation(matcher):
    verdict, names = check(matcher, "  manchester PICCADILLY ")
    assert verdict is Verdict.MATCH
    assert names == ["Manchester Piccadilly"]


@pytest.mark.parametrize(
    ("value", "station", "kind"),
    [
        ("Piccadilly", "Manchester Piccadilly", "shorthand"),
        ("Allerton", "Liverpool South Parkway", "former_name"),
        ("Clapham Jn", "Clapham Junction", "abbreviation"),
        ("Lime St", "Liverpool Lime Street", "shorthand"),
        ("MNCRPIC", "Manchester Piccadilly", "code"),
        ("9100MNCRPIC", "Manchester Piccadilly", "code"),
        ("ALERTN", "Liverpool South Parkway", "code"),
    ],
)
def test_alias(matcher, value, station, kind):
    result = matcher.validate(value)
    assert result.verdict is Verdict.ALIAS
    assert result.proposed.name == station
    assert result.proposed.via_kind == kind


@pytest.mark.parametrize(
    ("value", "station"),
    [
        ("Manchester Picadilly", "Manchester Piccadilly"),
        ("Liverpol Lime Street", "Liverpool Lime Street"),
        ("Readng", "Reading"),
        ("Sheffeild", "Sheffield"),  # adjacent letters swapped: single slip
        ("Stcokport", "Stockport"),
    ],
)
def test_typo(matcher, value, station):
    result = matcher.validate(value)
    assert result.verdict is Verdict.TYPO
    assert result.proposed.name == station


def test_ambiguous_fuzzy_ranks_candidates(matcher):
    verdict, names = check(matcher, "London Kings X")
    assert verdict is Verdict.AMBIGUOUS
    assert names[0] == "London Kings Cross"


def test_unknown(matcher):
    assert matcher.validate("Head Office").verdict is Verdict.UNKNOWN
    assert matcher.validate("").verdict is Verdict.UNKNOWN


# -- safety rules -----------------------------------------------------------


@pytest.mark.parametrize("city", ["Manchester", "Liverpool", "London", "Glasgow", "manchester"])
def test_city_names_are_never_auto_corrected(matcher, city):
    result = matcher.validate(city)
    assert result.verdict is Verdict.AMBIGUOUS
    assert result.proposed is None
    assert len(result.candidates) >= 2


def test_misspelt_city_is_still_ambiguous(matcher):
    # Fuzzy matching onto a multi-station alias must not pick one station.
    result = matcher.validate("Manchster")
    assert result.verdict is Verdict.AMBIGUOUS


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Waterloo", {"London Waterloo", "Waterloo (Merseyside)"}),
        ("Victoria", {"London Victoria", "Manchester Victoria"}),
        ("Charing Cross", {"London Charing Cross", "Charing Cross (Glasgow)"}),
        ("Ashford", {"Ashford (Surrey)", "Ashford International"}),
    ],
)
def test_shared_aliases_are_ambiguous(matcher, value, expected):
    verdict, names = check(matcher, value)
    assert verdict is Verdict.AMBIGUOUS
    assert set(names) == expected


def test_codes_never_take_part_in_fuzzy_matching(matcher):
    # One letter away from MNCRPIC, but a near-miss code is never trusted.
    assert matcher.validate("MNCRPIX").verdict is Verdict.UNKNOWN


def test_short_names_need_review_not_correction(matcher):
    # "Leds" is one edit from Leeds, but 4 characters is too short to trust.
    verdict, names = check(matcher, "Leds")
    assert verdict is Verdict.AMBIGUOUS
    assert names[0] == "Leeds"


def test_alias_is_checked_before_fuzzy(matcher):
    # "Allerton" is closer by spelling to West Allerton, but the alias table decides.
    result = matcher.validate("Allerton")
    assert result.verdict is Verdict.ALIAS
    assert result.proposed.name == "Liverpool South Parkway"


def test_short_form_explained_as_alias_not_code(matcher):
    # "Euston" is also the TIPLOC EUSTON; the human-readable alias is preferred.
    assert matcher.validate("Euston").proposed.via_kind == "shorthand"

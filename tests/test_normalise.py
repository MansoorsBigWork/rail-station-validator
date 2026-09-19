import pytest

from railvalidator.normalise import normalise


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Manchester Piccadilly", "manchester piccadilly"),
        ("  MANCHESTER   piccadilly  ", "manchester piccadilly"),
        ("King's Cross", "kings cross"),
        ("King\u2019s Cross", "kings cross"),
        ("Highbury & Islington", "highbury and islington"),
        ("Chester-le-Street", "chester le street"),
        ("Marne-la-Vall\u00e9e", "marne la vallee"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalise(raw, expected):
    assert normalise(raw) == expected


def test_st_is_never_expanded():
    # "St" means Street in "Lime St" and Saint in "St Erth"; normalisation must not guess.
    assert normalise("Lime St") == "lime st"
    assert normalise("St Erth") == "st erth"

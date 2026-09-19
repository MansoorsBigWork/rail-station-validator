"""Text normalisation shared by the catalog builder and the matcher.

Normalisation removes differences that never change meaning (case, accents,
punctuation, "&" versus "and", repeated spaces). It deliberately does NOT
expand abbreviations such as "St", because "St" means Street in
"Liverpool Lime St" and Saint in "St Erth". Abbreviations are handled as
explicit aliases instead, so every rewrite is traceable.
"""

from __future__ import annotations

import re
import unicodedata

_APOSTROPHES = re.compile(r"['\u2018\u2019`]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise(text: object) -> str:
    """Return a comparison key for a station name or code.

    >>> normalise("  King's Cross ")
    'kings cross'
    >>> normalise("Highbury & Islington")
    'highbury and islington'
    >>> normalise("Marne-la-Vallée")
    'marne la vallee'
    """
    if text is None:
        return ""
    s = str(text)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("&", " and ")
    s = _APOSTROPHES.sub("", s)
    s = _NON_ALNUM.sub(" ", s)
    return " ".join(s.split())

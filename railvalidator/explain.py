"""Plain-language explanations for each verdict.

Every sentence is built from a template filled only with catalog data (the
official name, its codes, the alias entry and its recorded source, or a
similarity score). The explanation therefore cannot state anything the
reference data does not contain.

If an LLM were ever added to smooth the wording, it would sit behind
``explain`` and receive this grounded text as its only input, and every
proposed change would still pass through the review step.
"""

from __future__ import annotations

from rapidfuzz.distance import OSA

from railvalidator.catalog import Catalog
from railvalidator.matcher import TYPO_THRESHOLD, Candidate, Result, Verdict
from railvalidator.normalise import normalise

_KIND_LABEL = {
    "shorthand": "an accepted short form",
    "former_name": "a former name",
    "city": "a city name",
    "qualifier_dropped": "the official name without its bracketed qualifier",
    "abbreviation": "a standard abbreviation",
}


def _codes(catalog: Catalog, cand: Candidate) -> str:
    codes = catalog.station(cand.station_id).codes
    label = "TIPLOC code" if len(codes) == 1 else "TIPLOC codes"
    return f"{label} {', '.join(codes)}"


def _via(cand: Candidate) -> str:
    if cand.via_kind == "name":
        return f"the official name '{cand.name}'"
    label = _KIND_LABEL.get(cand.via_kind, "an accepted alias")
    return f"'{cand.via}', {label} of {cand.name}"


def explain(result: Result, catalog: Catalog) -> str:
    value, cands = result.value, result.candidates

    if result.verdict is Verdict.MATCH:
        c = cands[0]
        return f"'{value}' is the official NaPTAN name of {c.name} ({_codes(catalog, c)})."

    if result.verdict is Verdict.ALIAS:
        c = cands[0]
        if c.via_kind == "code":
            return f"'{value}' is a NaPTAN TIPLOC code for {c.name} ({_codes(catalog, c)})."
        label = _KIND_LABEL.get(c.via_kind, "an accepted alias")
        return f"'{value}' is {label} of {c.name}. Source: {c.source}."

    if result.verdict is Verdict.TYPO:
        c = cands[0]
        if c.score < TYPO_THRESHOLD and OSA.distance(normalise(value), normalise(c.via)) == 1:
            text = f"'{value}' differs by one character from {_via(c)} ({c.score:.0f}% similar)"
        else:
            text = f"'{value}' is {c.score:.0f}% similar to {_via(c)}"
        if len(cands) > 1:
            text += f"; the next closest station, {cands[1].name}, scores {cands[1].score:.0f}%"
        return text + "."

    if result.verdict is Verdict.AMBIGUOUS:
        names = ", ".join(c.name for c in cands)
        if all(c.via_kind == "city" for c in cands):
            return (
                f"'{value}' is a city name, not a station. "
                f"It covers {len(cands)} stations: {names}. Choose the station meant."
            )
        if cands[0].score == 100:
            return (
                f"'{value}' is an accepted name for {len(cands)} different stations: {names}. Choose the station meant."
            )
        return (
            f"'{value}' is not close enough to any single station to correct automatically. "
            f"Closest: {'; '.join(f'{c.name} ({c.score:.0f}%)' for c in cands)}."
        )

    if not value:
        return "The cell is empty."
    return f"No station name, code or alias is at least 70% similar to '{value}'."

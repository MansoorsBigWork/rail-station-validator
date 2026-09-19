"""Validation of a whole submission, and applying a reviewer's decisions.

This module holds no UI code, so the same logic drives the CLI, the web app
and the tests.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from railvalidator.catalog import Catalog
from railvalidator.explain import explain
from railvalidator.matcher import Matcher, Result, Verdict

STATION_COLUMNS = ("from_station", "to_station")


@dataclass(frozen=True)
class Finding:
    row: int  # position in the submission DataFrame (0-based)
    column: str
    result: Result
    explanation: str

    @property
    def verdict(self) -> Verdict:
        return self.result.verdict

    @property
    def value(self) -> str:
        return self.result.value

    @property
    def proposed_name(self) -> str | None:
        """The correction to offer, or None if a person must choose."""
        cand = self.result.proposed
        if cand is None or cand.name == self.value:
            return None
        return cand.name


@dataclass(frozen=True)
class Change:
    row: int
    column: str
    old: str
    new: str
    verdict: str
    reason: str


def validate_submission(
    df: pd.DataFrame, catalog: Catalog, matcher: Matcher | None = None, columns=STATION_COLUMNS
) -> list[Finding]:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Submission is missing required columns: {missing}")
    matcher = matcher or Matcher(catalog)
    findings = []
    for column in columns:
        for row, value in enumerate(df[column].tolist()):
            text = "" if pd.isna(value) else str(value)
            result = matcher.validate(text)
            findings.append(Finding(row, column, result, explain(result, catalog)))
    return sorted(findings, key=lambda f: (f.row, columns.index(f.column)))


def summarise(findings: list[Finding]) -> dict[str, int]:
    counts = {v.value: 0 for v in Verdict}
    for f in findings:
        counts[f.verdict.value] += 1
    return counts


def default_decisions(findings: list[Finding]) -> dict[tuple[int, str], str]:
    """Every single proposed correction, as the starting point for review.

    AMBIGUOUS and UNKNOWN values are never included: they need a person.
    """
    return {(f.row, f.column): f.proposed_name for f in findings if f.proposed_name is not None}


def apply_decisions(
    df: pd.DataFrame, findings: list[Finding], decisions: dict[tuple[int, str], str]
) -> tuple[pd.DataFrame, list[Change]]:
    """Return a corrected copy of the submission and a log of every change.

    The input DataFrame is never modified.
    """
    by_cell = {(f.row, f.column): f for f in findings}
    corrected = df.copy()
    changes: list[Change] = []
    for (row, column), new in sorted(decisions.items()):
        finding = by_cell.get((row, column))
        if finding is None:
            raise KeyError(f"No finding for row {row}, column {column!r}")
        old = finding.value
        if not new or new == old:
            continue
        corrected.iat[row, corrected.columns.get_loc(column)] = new
        changes.append(Change(row, column, old, new, finding.verdict.value, finding.explanation))
    return corrected, changes

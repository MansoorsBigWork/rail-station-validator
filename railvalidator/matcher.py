"""Tiered validation pipeline.

Each submitted value is checked in a fixed order, and the first tier that
applies decides the verdict:

    1. MATCH      the value is an official station name (after normalisation)
    2. ALIAS      the value is an accepted alias that identifies exactly one
                  station, or a NaPTAN TIPLOC / ATCO code
    3. AMBIGUOUS  the value is an accepted alias shared by several stations
                  (for example "Manchester" or "Victoria")
    4. TYPO       fuzzy similarity >= 92% to one station, or a single-character
                  slip (one insertion, deletion, substitution or swap of
                  adjacent letters) in a name of 6+ characters, in both cases
                  with no other station within the safety margin
    5. AMBIGUOUS  fuzzy similarity between 70% and 92%, or several stations
                  close together at the top
    6. UNKNOWN    nothing is at least 70% similar

Deterministic tiers (1 to 3) always run before fuzzy matching, so a value
is only ever corrected by similarity when no exact rule covers it. Station
codes never take part in fuzzy matching: codes such as MNCRPIC and MNCRVIC
differ by a letter or two, and a near-miss code is exactly where a
similarity score would pick the wrong station.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from rapidfuzz import fuzz, process
from rapidfuzz.distance import OSA

from railvalidator.catalog import Alias, Catalog
from railvalidator.normalise import normalise

TYPO_THRESHOLD = 92.0
AMBIGUOUS_THRESHOLD = 70.0
TYPO_MARGIN = 5.0  # the runner-up must trail the best station by at least this much
MAX_CANDIDATES = 5
# A percentage threshold is harsh on short names: one slip in "Sheffield"
# scores only 89%. A single edit is therefore also accepted as a typo, but
# only for names long enough that one edit rarely lands on another station.
SINGLE_EDIT_MIN_LENGTH = 6


class Verdict(StrEnum):
    MATCH = "MATCH"
    ALIAS = "ALIAS"
    TYPO = "TYPO"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"

    @property
    def needs_review(self) -> bool:
        return self is not Verdict.MATCH


@dataclass(frozen=True)
class Candidate:
    """A station the value might refer to, with the evidence for it."""

    station_id: str
    name: str
    score: float  # 0 to 100; 100 for deterministic hits
    via: str  # the accepted form that matched (official name, alias text or code)
    via_kind: str  # "name", "code" or an Alias kind
    source: str = ""


@dataclass(frozen=True)
class Result:
    value: str
    verdict: Verdict
    candidates: tuple[Candidate, ...] = field(default_factory=tuple)

    @property
    def proposed(self) -> Candidate | None:
        """The single correction proposed, for MATCH, ALIAS and TYPO only."""
        if self.verdict in (Verdict.MATCH, Verdict.ALIAS, Verdict.TYPO):
            return self.candidates[0]
        return None


class Matcher:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        # Fuzzy choices: official names and name-like aliases, never codes.
        self._choice_keys: list[str] = []
        self._choice_meta: list[tuple[tuple[str, ...], str, str, str]] = []
        for key, sid in catalog.by_name.items():
            self._choice_keys.append(key)
            self._choice_meta.append(((sid,), catalog.station(sid).name, "name", ""))
        for key, entries in catalog.aliases.items():
            ids, _ = catalog.alias_targets(key)
            first = entries[0]
            self._choice_keys.append(key)
            self._choice_meta.append((tuple(ids), first.text, first.kind, first.source))
        self._cache: dict[str, Result] = {}

    def validate(self, value: object) -> Result:
        text = "" if value is None else str(value).strip()
        if text in self._cache:
            return self._cache[text]
        result = self._validate(text)
        self._cache[text] = result
        return result

    # -- tiers -------------------------------------------------------------

    def _validate(self, text: str) -> Result:
        key = normalise(text)
        if not key:
            return Result(text, Verdict.UNKNOWN)

        cat = self.catalog
        if key in cat.by_name:
            sid = cat.by_name[key]
            return Result(text, Verdict.MATCH, (self._candidate(sid, 100, cat.station(sid).name, "name"),))

        ids, entries = cat.alias_targets(key)
        if len(ids) == 1:
            return Result(text, Verdict.ALIAS, (self._alias_candidate(ids[0], entries),))

        # Checked after unique aliases so that "Euston" is explained as a
        # short form of London Euston, not as its TIPLOC code EUSTON.
        code = text.upper()
        if code.startswith("9100"):
            code = code[4:]
        if " " not in code and code in cat.by_code:
            sid = cat.by_code[code]
            return Result(text, Verdict.ALIAS, (self._candidate(sid, 100, code, "code"),))

        if ids:
            return Result(text, Verdict.AMBIGUOUS, tuple(self._alias_candidate(sid, entries) for sid in ids))

        return self._fuzzy(text, key)

    def _fuzzy(self, text: str, key: str) -> Result:
        hits = process.extract(
            key,
            self._choice_keys,
            scorer=fuzz.ratio,
            score_cutoff=AMBIGUOUS_THRESHOLD,
            limit=50,
        )
        best: dict[str, Candidate] = {}
        for _, score, index in hits:
            ids, via, kind, source = self._choice_meta[index]
            for sid in ids:
                if sid not in best or score > best[sid].score:
                    best[sid] = self._candidate(sid, round(score, 1), via, kind, source)
        ranked = sorted(best.values(), key=lambda c: (-c.score, c.name))[:MAX_CANDIDATES]
        if not ranked:
            return Result(text, Verdict.UNKNOWN)

        top = ranked[0]
        runner_up = ranked[1].score if len(ranked) > 1 else 0.0
        single_slip = len(key) >= SINGLE_EDIT_MIN_LENGTH and OSA.distance(key, normalise(top.via)) == 1
        if (top.score >= TYPO_THRESHOLD or single_slip) and top.score - runner_up >= TYPO_MARGIN:
            return Result(text, Verdict.TYPO, tuple(ranked))
        return Result(text, Verdict.AMBIGUOUS, tuple(ranked))

    # -- helpers -----------------------------------------------------------

    def _candidate(self, sid: str, score: float, via: str, kind: str, source: str = "") -> Candidate:
        return Candidate(sid, self.catalog.station(sid).name, score, via, kind, source)

    def _alias_candidate(self, sid: str, entries: list[Alias]) -> Candidate:
        entry = next(a for a in entries if sid in a.station_ids)
        return self._candidate(sid, 100, entry.text, entry.kind, entry.source)

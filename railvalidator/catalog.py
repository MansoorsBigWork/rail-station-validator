"""Reference catalog of UK rail stations.

Two jobs live here:

1. ``build_from_naptan`` turns the raw NaPTAN ``Stops.csv`` (hundreds of
   thousands of bus stops, platforms and entrances) into one clean row per
   rail station, and records every data-quality fix it makes.
2. ``Catalog`` loads that clean station list plus the hand-maintained alias
   file and builds the lookup indexes the matcher uses.
"""

from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from railvalidator.normalise import normalise

RAIL_STOP_TYPE = "RLY"
RAIL_ATCO_PREFIX = "9100"

# Records sharing a cleaned name are merged only if they are this close.
MERGE_DISTANCE_KM = 2.0

# Suffixes NaPTAN appends inconsistently to rail station names.
_NAME_SUFFIXES = (
    re.compile(r"\s*\(Rail Station\)$"),
    re.compile(r"\s+Rail(way)? Station$"),
    re.compile(r"\s+Metro Station$"),
    re.compile(r"\s+Station$"),
)

# Safe one-way abbreviations: the full word appears in the official name, the
# short form is accepted as an alias. "St" is never expanded because it means
# both Street and Saint.
_ABBREVIATIONS = {"street": "st", "junction": "jn", "road": "rd"}

_QUALIFIER = re.compile(r"^(?P<base>.+?)\s*\((?P<qualifier>[^)]+)\)$")

STATION_COLUMNS = [
    "station_id",
    "name",
    "codes",
    "atco",
    "locality",
    "parent_locality",
    "lat",
    "lon",
]


# --------------------------------------------------------------------------
# Building the catalog from raw NaPTAN
# --------------------------------------------------------------------------


def clean_station_name(common_name: str) -> str:
    """Strip NaPTAN's inconsistent 'Rail Station' style suffixes."""
    name = " ".join(str(common_name).split())
    for pattern in _NAME_SUFFIXES:
        name = pattern.sub("", name)
    return name


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres (haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class BuildReport:
    """Every data-quality decision taken while building the catalog."""

    rail_records: int = 0
    inactive_dropped: list[str] = field(default_factory=list)
    names_cleaned: list[tuple[str, str]] = field(default_factory=list)
    no_coordinates_merged: list[tuple[str, str]] = field(default_factory=list)
    duplicates_merged: dict[str, list[str]] = field(default_factory=dict)
    kept_apart: list[str] = field(default_factory=list)
    no_coordinates_kept: list[str] = field(default_factory=list)
    stations: int = 0

    def to_markdown(self) -> str:
        def section(title: str, lines: list[str]) -> list[str]:
            out = [f"## {title} ({len(lines)})", ""]
            out += [f"- {line}" for line in lines] or ["- none"]
            return out + [""]

        lines = [
            "# Catalog build report",
            "",
            f"- Rail station records in NaPTAN (StopType {RAIL_STOP_TYPE}): {self.rail_records}",
            f"- Stations in the final catalog: {self.stations}",
            "",
        ]
        lines += section("Inactive records dropped", self.inactive_dropped)
        lines += section(
            "Names with non-standard suffixes cleaned",
            [f"`{raw}` became `{clean}`" for raw, clean in self.names_cleaned],
        )
        lines += section(
            "Records without coordinates merged into their full-name station",
            [f"`{raw}` merged into `{target}`" for raw, target in self.no_coordinates_merged],
        )
        lines += section(
            "Stations with several NaPTAN records merged into one",
            [f"`{name}`: {', '.join(codes)}" for name, codes in self.duplicates_merged.items()],
        )
        lines += section("Same-name records kept apart (too far apart to merge)", self.kept_apart)
        lines += section("Stations kept without coordinates", self.no_coordinates_kept)
        return "\n".join(lines)


def build_from_naptan(stops: pd.DataFrame) -> tuple[pd.DataFrame, BuildReport]:
    """Reduce a raw NaPTAN Stops table to one clean row per rail station."""
    report = BuildReport()
    rail = stops[stops["StopType"] == RAIL_STOP_TYPE].copy()
    report.rail_records = len(rail)

    inactive = rail[rail["Status"].str.lower() != "active"]
    report.inactive_dropped = sorted(f"{r.ATCOCode}: {r.CommonName}" for r in inactive.itertuples())
    rail = rail[rail["Status"].str.lower() == "active"].copy()

    rail["name"] = rail["CommonName"].map(clean_station_name)
    unusual = rail[~rail["CommonName"].str.endswith(" Rail Station") & (rail["CommonName"] != rail["name"])]
    report.names_cleaned = sorted(zip(unusual["CommonName"], unusual["name"], strict=True))

    rail["code"] = rail["ATCOCode"].map(
        lambda a: a[len(RAIL_ATCO_PREFIX) :] if str(a).startswith(RAIL_ATCO_PREFIX) else str(a)
    )
    rail["has_coords"] = rail["Latitude"].notna() & rail["Longitude"].notna()

    # Some records (mostly Elizabeth line entries) have no coordinates and a
    # shortened name, e.g. "Liverpool Street" for "London Liverpool Street".
    # Merge them into the full-name station when one exists.
    names_with_coords = set(rail.loc[rail["has_coords"], "name"])
    for idx, row in rail[~rail["has_coords"]].iterrows():
        for candidate in (f"London {row['name']}", f"{row['name']} (London)"):
            if candidate in names_with_coords:
                report.no_coordinates_merged.append((row["CommonName"], candidate))
                rail.at[idx, "name"] = candidate
                break

    rows = []
    for name, group in rail.groupby("name", sort=True):
        group = group.sort_values(["has_coords", "ModificationDateTime", "ATCOCode"], ascending=[False, False, True])
        primary = group.iloc[0]
        members = [group.iloc[0]]
        for _, other in group.iloc[1:].iterrows():
            far = (
                primary["has_coords"]
                and other["has_coords"]
                and _distance_km(primary["Latitude"], primary["Longitude"], other["Latitude"], other["Longitude"])
                > MERGE_DISTANCE_KM
            )
            if far:
                report.kept_apart.append(f"{name}: {primary['code']} and {other['code']}")
                rows.append(_station_row(f"{name} ({other['code']})", [other]))
            else:
                members.append(other)
        if len(members) > 1:
            report.duplicates_merged[name] = [m["code"] for m in members]
        if not primary["has_coords"]:
            report.no_coordinates_kept.append(f"{name} ({primary['code']})")
        rows.append(_station_row(name, members))

    stations = pd.DataFrame(rows, columns=STATION_COLUMNS).sort_values("name").reset_index(drop=True)
    report.stations = len(stations)
    return stations, report


def _station_row(name: str, members: list[pd.Series]) -> dict:
    primary = members[0]

    def clean(value: object) -> str:
        return "" if pd.isna(value) else str(value)

    return {
        "station_id": primary["code"],
        "name": name,
        "codes": "|".join(dict.fromkeys(m["code"] for m in members)),
        "atco": primary["ATCOCode"],
        "locality": clean(primary.get("LocalityName")),
        "parent_locality": clean(primary.get("ParentLocalityName")),
        "lat": primary["Latitude"],
        "lon": primary["Longitude"],
    }


# --------------------------------------------------------------------------
# Loading the catalog for validation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Station:
    station_id: str
    name: str
    codes: tuple[str, ...]
    atco: str
    locality: str
    parent_locality: str
    lat: float | None
    lon: float | None


@dataclass(frozen=True)
class Alias:
    """An accepted alternative form that maps to one or more stations."""

    text: str
    station_ids: tuple[str, ...]
    kind: str  # shorthand | former_name | city | qualifier_dropped | abbreviation
    source: str


class CatalogError(ValueError):
    """Raised when the catalog or alias file is inconsistent."""


class Catalog:
    def __init__(self, stations: list[Station], aliases: list[Alias]):
        self.stations: dict[str, Station] = {s.station_id: s for s in stations}
        self.by_name: dict[str, str] = {}
        self.by_code: dict[str, str] = {}
        for s in stations:
            key = normalise(s.name)
            if key in self.by_name:
                raise CatalogError(f"Two stations normalise to the same name: {s.name!r}")
            self.by_name[key] = s.station_id
            for code in s.codes:
                self.by_code[code.upper()] = s.station_id

        # normalised alias text -> all Alias entries using that text
        self.aliases: dict[str, list[Alias]] = defaultdict(list)
        for alias in aliases:
            key = normalise(alias.text)
            if key in self.by_name:
                continue  # an official name always wins over an alias
            self.aliases[key].append(alias)

    def __len__(self) -> int:
        return len(self.stations)

    def station(self, station_id: str) -> Station:
        return self.stations[station_id]

    def alias_targets(self, key: str) -> tuple[list[str], list[Alias]]:
        """Station ids (deduplicated, in order) and the alias entries for a key."""
        entries = self.aliases.get(key, [])
        ids = list(dict.fromkeys(sid for a in entries for sid in a.station_ids))
        return ids, entries

    # -- loading ---------------------------------------------------------

    @classmethod
    def load(cls, stations_csv: Path | str, aliases_csv: Path | str | None = None) -> Catalog:
        stations = load_stations(stations_csv)
        by_name = {s.name: s.station_id for s in stations}
        aliases = derived_aliases(stations)
        if aliases_csv is not None:
            hand = load_alias_file(aliases_csv, by_name)
            aliases += hand + [a for a in map(abbreviated, hand) if a is not None]
        return cls(stations, aliases)


def load_stations(path: Path | str) -> list[Station]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = set(STATION_COLUMNS) - set(df.columns)
    if missing:
        raise CatalogError(f"{path} is missing columns: {sorted(missing)}")

    def coord(value: str) -> float | None:
        return float(value) if value else None

    return [
        Station(
            station_id=r["station_id"],
            name=r["name"],
            codes=tuple(c for c in r["codes"].split("|") if c),
            atco=r["atco"],
            locality=r["locality"],
            parent_locality=r["parent_locality"],
            lat=coord(r["lat"]),
            lon=coord(r["lon"]),
        )
        for _, r in df.iterrows()
    ]


def abbreviate(text: str) -> str | None:
    """Short form of a name using the safe abbreviations, or None if none apply."""
    words = normalise(text).split()
    if not any(w in _ABBREVIATIONS for w in words):
        return None
    return " ".join(_ABBREVIATIONS.get(w, w) for w in words)


def abbreviated(alias: Alias) -> Alias | None:
    """Abbreviated copy of an alias ("Lime Street" gives "Lime St")."""
    short = abbreviate(alias.text)
    if short is None:
        return None
    return Alias(short, alias.station_ids, alias.kind, f"abbreviation of {alias.text!r}: {alias.source}")


def derived_aliases(stations: list[Station]) -> list[Alias]:
    """Aliases generated by rule from the official names themselves."""
    out: list[Alias] = []
    keys = [(normalise(s.name), s) for s in stations]
    for s in stations:
        m = _QUALIFIER.match(s.name)
        if m:
            # "Ashford" is Ashford (Surrey) without its qualifier, but it is also
            # how people write Ashford International. Any station whose name
            # starts with the same words shares the alias, so it stays ambiguous.
            base = normalise(m.group("base"))
            others = tuple(o.station_id for k, o in keys if o is not s and k.startswith(base + " "))
            source = f"official name {s.name!r} without its bracketed qualifier"
            if others:
                source += "; other station names also start with these words"
            out.append(Alias(m.group("base"), (s.station_id, *others), "qualifier_dropped", source))
        short = abbreviate(s.name)
        if short is not None:
            out.append(
                Alias(
                    text=short,
                    station_ids=(s.station_id,),
                    kind="abbreviation",
                    source=f"standard abbreviation of {s.name!r}",
                )
            )
    return out


def load_alias_file(path: Path | str, by_name: dict[str, str]) -> list[Alias]:
    """Read the hand-maintained alias file.

    Columns: alias, targets (official names separated by '|'), kind, source.
    Every target must be an official station name, so the alias file cannot
    silently drift away from the catalog.
    """
    aliases: list[Alias] = []
    unknown: list[str] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            targets = [t.strip() for t in row["targets"].split("|") if t.strip()]
            ids = []
            for t in targets:
                if t in by_name:
                    ids.append(by_name[t])
                else:
                    unknown.append(f"line {line_no}: {t!r}")
            if ids:
                aliases.append(Alias(row["alias"].strip(), tuple(ids), row["kind"].strip(), row["source"].strip()))
    if unknown:
        raise CatalogError("Alias targets not found in the catalog: " + "; ".join(unknown))
    return aliases

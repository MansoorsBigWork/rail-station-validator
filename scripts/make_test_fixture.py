"""Write tests/fixtures/stations.csv: a small, fixed extract of the catalog.

Tests run against this extract rather than the full catalog, so they stay
fast and never change when NaPTAN is refreshed. It contains every station
named in data/aliases.csv plus the look-alike stations the tests rely on.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

EXTRA = [
    "Ashford (Surrey)",
    "Ashford International",
    "Clifton (Manchester)",
    "Clifton Down",
    "Waterloo (Merseyside)",
    "London Waterloo East",
    "Charing Cross (Glasgow)",
    "Newport (Essex)",
    "Newport (S Wales)",
    "Sheffield",
    "Shenfield",
    "Ashfield",
    "Stockport",
    "Reading",
    "Brading",
    "Leeds",
    "York",
    "Crewe",
    "Crowle",
    "Crawley",
    "Brighton",
    "Bridgeton",
    "Brixton",
    "Doncaster",
    "Ancaster",
    "Lancaster",
    "Newark Castle",
    "Wimbledon",
    "Clapham Junction",
    "Heathrow Terminal 5",
    "Liverpool James Street",
    "West Allerton",
    "Wilmslow",
    "Preston",
    "Leicester",
]


def main() -> None:
    stations = pd.read_csv(ROOT / "data" / "stations.csv", dtype=str, keep_default_na=False)
    wanted = set(EXTRA)
    with open(ROOT / "data" / "aliases.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            wanted.update(t.strip() for t in row["targets"].split("|"))
    subset = stations[stations["name"].isin(wanted)]
    missing = wanted - set(subset["name"])
    if missing:
        raise SystemExit(f"Not in catalog: {sorted(missing)}")
    out = ROOT / "tests" / "fixtures" / "stations.csv"
    subset.to_csv(out, index=False)
    print(f"Wrote {len(subset)} stations to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Generate sample_submission.xlsx: synthetic travel expense claims with seeded errors.

Every station value below is chosen to exercise a specific verdict, so the
sample shows each tier of the pipeline. The people and fares are invented.
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

CORRECT = [
    "Manchester Piccadilly",
    "Liverpool Lime Street",
    "London Euston",
    "Leeds",
    "York",
    "Birmingham New Street",
    "Sheffield",
    "Stockport",
    "Crewe",
    "Reading",
    "London Kings Cross",
    "Bristol Temple Meads",
    "Glasgow Central",
    "Newcastle",
    "Wilmslow",
    "Preston",
    "Leicester",
]
ALIAS = [
    "MNCRPIC",
    "9100LVRPLSH",
    "Lime St",
    "Kings Cross",
    "Euston",
    "Piccadilly",
    "Allerton",
    "Edinburgh Waverley",
    "Birmingham New St",
    "Clapham Jn",
    "Leeds City",
    "Temple Meads",
    "Bath",
    "St Pancras",
]
TYPO = [
    "Manchester Picadilly",
    "Liverpol Lime Street",
    "Sheffeild",
    "Stcokport",
    "Newcastel",
    "Readng",
    "Brigton",
    "Doncater",
    "Wimbeldon",
]
AMBIGUOUS = [
    "Manchester",
    "Victoria",
    "Waterloo",
    "Ashford",
    "London",
    "Clifton",
    "Newport",
    "Glasgow",
    "Leds",
    "Heathrow T5",
    "London Kings X",
]
UNKNOWN = ["Head Office", "Client site", "Atlantis", ""]

EMPLOYEES = ["A. Patel", "B. Okafor", "C. Nowak", "D. Hughes", "E. Rahman", "F. Lindqvist", "G. Byrne"]


def build(seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    seeded = ALIAS + TYPO + AMBIGUOUS + UNKNOWN
    rng.shuffle(seeded)
    rows = []
    for i, bad in enumerate(seeded):
        good = rng.choice(CORRECT)
        from_station, to_station = (bad, good) if i % 2 == 0 else (good, bad)
        rows.append((from_station, to_station))
    # Fully correct claims so the report is realistic, not all errors.
    for _ in range(12):
        a, b = rng.sample(CORRECT, 2)
        rows.append((a, b))
    rng.shuffle(rows)
    return pd.DataFrame(
        [
            {
                "claim_id": f"EXP-{1001 + i}",
                "employee": rng.choice(EMPLOYEES),
                "travel_date": f"2026-{rng.randint(1, 8):02d}-{rng.randint(1, 28):02d}",
                "from_station": a,
                "to_station": b,
                "fare_gbp": f"{rng.uniform(4, 180):.2f}",
            }
            for i, (a, b) in enumerate(rows)
        ]
    )


def main() -> None:
    out = ROOT / "sample_submission.xlsx"
    build().to_excel(out, index=False)
    print(f"Wrote {out.name}")


if __name__ == "__main__":
    main()

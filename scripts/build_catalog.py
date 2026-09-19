"""Build data/stations.csv from the NaPTAN Stops file.

Usage:
    python scripts/build_catalog.py path/to/Stops.csv
    python scripts/build_catalog.py --download

--download fetches the current CSV from the Department for Transport's
NaPTAN API. The raw file is about 100 MB, so it is saved under raw/ (which
is git-ignored) and only the small cleaned catalog is committed.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from railvalidator.catalog import build_from_naptan  # noqa: E402

NAPTAN_CSV_URL = "https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv"
USECOLS = [
    "ATCOCode",
    "CommonName",
    "LocalityName",
    "ParentLocalityName",
    "Longitude",
    "Latitude",
    "StopType",
    "Status",
    "ModificationDateTime",
]


def download(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading NaPTAN from {NAPTAN_CSV_URL} ...")
    urllib.request.urlretrieve(NAPTAN_CSV_URL, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stops_csv", nargs="?", type=Path, help="NaPTAN Stops.csv")
    parser.add_argument("--download", action="store_true", help="download the latest NaPTAN CSV first")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "stations.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "build_report.md")
    args = parser.parse_args(argv)

    if args.download:
        source = download(ROOT / "raw" / "Stops.csv")
    elif args.stops_csv:
        source = args.stops_csv
    else:
        parser.error("give a Stops.csv path or use --download")

    stops = pd.read_csv(source, usecols=USECOLS, dtype={"ATCOCode": str}, low_memory=False)
    stations, report = build_from_naptan(stops)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    stations.to_csv(args.out, index=False)
    args.report.write_text(report.to_markdown(), encoding="utf-8")
    print(f"{report.rail_records} rail records -> {report.stations} stations")
    print(f"Catalog: {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
    print(f"Report:  {args.report.relative_to(ROOT) if args.report.is_relative_to(ROOT) else args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

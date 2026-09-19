"""Headless validation: python -m railvalidator.cli submission.xlsx"""

from __future__ import annotations

import argparse
from pathlib import Path

from railvalidator.catalog import Catalog
from railvalidator.excel_io import build_commit_workbook, build_report_workbook, read_submission
from railvalidator.review import apply_decisions, default_decisions, summarise, validate_submission

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate station names in a travel expense submission.")
    parser.add_argument("submission", type=Path, nargs="?", default=Path("sample_submission.xlsx"))
    parser.add_argument("--stations", type=Path, default=DATA_DIR / "stations.csv")
    parser.add_argument("--aliases", type=Path, default=DATA_DIR / "aliases.csv")
    parser.add_argument("--out", type=Path, default=Path("validation_results.xlsx"))
    parser.add_argument(
        "--proposed",
        type=Path,
        help="also write a workbook with every single proposed correction applied, for bulk review",
    )
    parser.add_argument("--fail-on-review", action="store_true", help="exit with status 1 if any cell needs review")
    args = parser.parse_args(argv)

    catalog = Catalog.load(args.stations, args.aliases)
    df = read_submission(args.submission)
    findings = validate_submission(df, catalog)

    build_report_workbook(df, findings).save(args.out)
    counts = summarise(findings)
    width = max(len(k) for k in counts)
    print(f"Validated {len(findings)} station cells in {args.submission} against {len(catalog)} stations")
    for verdict, n in counts.items():
        print(f"  {verdict.ljust(width)}  {n}")
    print(f"Report written to {args.out}")

    if args.proposed:
        corrected, changes = apply_decisions(df, findings, default_decisions(findings))
        build_commit_workbook(corrected, changes).save(args.proposed)
        print(f"{len(changes)} proposed corrections written to {args.proposed} (original unchanged)")

    needs_review = sum(n for v, n in counts.items() if v != "MATCH")
    return 1 if args.fail_on_review and needs_review else 0


if __name__ == "__main__":
    raise SystemExit(main())

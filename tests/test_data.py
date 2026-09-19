"""Integrity checks on the committed full catalog."""

from pathlib import Path

from railvalidator.catalog import Catalog

ROOT = Path(__file__).resolve().parents[1]


def test_full_catalog_loads_with_aliases():
    catalog = Catalog.load(ROOT / "data" / "stations.csv", ROOT / "data" / "aliases.csv")
    assert len(catalog) > 2500
    assert catalog.by_code["MNCRPIC"] == catalog.by_name["manchester piccadilly"]

from pathlib import Path

import pytest

from railvalidator.catalog import Catalog
from railvalidator.matcher import Matcher

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_STATIONS = ROOT / "tests" / "fixtures" / "stations.csv"
ALIASES = ROOT / "data" / "aliases.csv"


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog.load(FIXTURE_STATIONS, ALIASES)


@pytest.fixture(scope="session")
def matcher(catalog) -> Matcher:
    return Matcher(catalog)

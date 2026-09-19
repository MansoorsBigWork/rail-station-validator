import pandas as pd
import pytest

from railvalidator.catalog import Catalog, CatalogError, build_from_naptan, clean_station_name, load_alias_file


def stop(atco, name, lat=53.0, lon=-2.0, status="active", stop_type="RLY", modified="2024-01-01"):
    return {
        "ATCOCode": atco,
        "CommonName": name,
        "LocalityName": "",
        "ParentLocalityName": "",
        "Latitude": lat,
        "Longitude": lon,
        "StopType": stop_type,
        "Status": status,
        "ModificationDateTime": modified,
    }


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("York Rail Station", "York"),
        ("Kintore Railway Station", "Kintore"),
        ("Brent Cross West Station", "Brent Cross West"),
        ("Coombe Junction Halt (Rail Station)", "Coombe Junction Halt"),
        ("Newcastle Airport Metro Station", "Newcastle Airport"),
        ("Clifton (Manchester) Rail Station", "Clifton (Manchester)"),
        ("Soham", "Soham"),
    ],
)
def test_clean_station_name(raw, clean):
    assert clean_station_name(raw) == clean


def test_build_filters_merges_and_reports():
    stops = pd.DataFrame(
        [
            stop("0100BUS1", "Temple Meads Stn", stop_type="BCT"),
            stop("9100YORK", "York Rail Station", 53.958, -1.093),
            stop("9100OLDSTN", "Old Station Rail Station (closed)", status="inactive"),
            stop("9100CLPHMJ1", "Clapham Junction Rail Station", 51.4641, -0.1702),
            stop("9100CLPHMJW", "Clapham Junction Rail Station", 51.4642, -0.1703),
            stop("9100LIVST", "London Liverpool Street Rail Station", 51.518, -0.081),
            stop("9100LIVSTLL", "Liverpool Street", None, None),
            stop("9100FARA", "Faraway Rail Station", 50.0, -5.0),
            stop("9100FARB", "Faraway Rail Station", 57.0, -3.0),
        ]
    )
    stations, report = build_from_naptan(stops)
    names = stations["name"].tolist()

    assert report.rail_records == 8
    assert report.inactive_dropped == ["9100OLDSTN: Old Station Rail Station (closed)"]
    assert "Old Station" not in " ".join(names)
    assert names.count("Clapham Junction") == 1
    clapham = stations[stations["name"] == "Clapham Junction"].iloc[0]
    assert set(clapham["codes"].split("|")) == {"CLPHMJ1", "CLPHMJW"}
    assert ("Liverpool Street", "London Liverpool Street") in report.no_coordinates_merged
    assert "Liverpool Street" not in names
    # Same name, 800 km apart: two different stations, never merged.
    assert len(report.kept_apart) == 1
    assert sum(n.startswith("Faraway") for n in names) == 2


def test_alias_file_rejects_unknown_targets(tmp_path):
    path = tmp_path / "aliases.csv"
    path.write_text("alias,targets,kind,source\nNowhere,No Such Station,shorthand,test\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="No Such Station"):
        load_alias_file(path, {"York": "YORK"})


def test_official_name_beats_alias(catalog: Catalog):
    # Every official name is looked up as a name, never through an alias.
    for key in catalog.by_name:
        assert key not in catalog.aliases


def test_qualifier_alias_is_shared_with_prefix_stations(catalog: Catalog):
    ids, _ = catalog.alias_targets("ashford")
    assert {catalog.station(i).name for i in ids} == {"Ashford (Surrey)", "Ashford International"}

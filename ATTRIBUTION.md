# Data attribution

`data/stations.csv` and `tests/fixtures/stations.csv` are derived from the
National Public Transport Access Nodes (NaPTAN) dataset published by the
Department for Transport.

Contains public sector information licensed under the Open Government Licence v3.0.
https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/

Changes made to the source data are listed in `data/build_report.md`:
rail station records only, inactive records removed, name suffixes cleaned,
and records that describe the same station merged.

`data/aliases.csv` is maintained by hand for this project. Each row records
its own source.

`sample_submission.xlsx` is synthetic. The people, dates and fares are invented.

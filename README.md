# Rail Station Validator

![tests](https://github.com/YOUR-USERNAME/rail-station-validator/actions/workflows/tests.yml/badge.svg)

A human-in-the-loop tool for validating UK rail station names in travel
expense claims against the Department for Transport's NaPTAN register of
2,644 stations. It automates the tedious part (checking every cell for
codes, short forms, former names and typos) while keeping the judgement
calls with a person, who reviews every proposed correction and commits
approved changes to a new workbook in one batch.

## UI Screen shots



**Pre-upload**
<img width="1906" height="915" alt="image" src="https://github.com/user-attachments/assets/325cd7e8-9c7a-4205-a5b3-f58d6f9dd829" />



**Post-upload**
<img width="1900" height="921" alt="image" src="https://github.com/user-attachments/assets/de6476b9-88cd-4b69-927e-918fadc36f6b" />



**Excel-upload** 
<img width="872" height="681" alt="image" src="https://github.com/user-attachments/assets/b7f5a3b4-6691-49f7-8d58-9a6848a2aafc" />



## Why this exists

Finance teams check thousands of expense claims where staff type station
names however they like. The same journey arrives as `Manchester Piccadilly`,
`Piccadilly`, `MNCRPIC`, `Manchester Picadilly` or just `Manchester`.
Reconciling this by hand is slow, and the two obvious automations both fail:

* **Exact matching** rejects harmless variants such as `Lime St` or `King's Cross`.
* **Unguarded fuzzy matching** confidently picks the wrong station, because
  UK station names collide constantly. `Waterloo` is both London Waterloo and
  Waterloo (Merseyside). `Ashford` is both Ashford International and Ashford
  (Surrey). `Victoria` exists in London and Manchester.

This tool uses a tiered pipeline where deterministic rules run first,
similarity is only trusted when it is near-certain and unique, and every
genuinely ambiguous value goes to a person with the candidates ranked and
explained. Nothing changes without explicit approval, and the original
submission is never modified.

## The validation tiers

| Verdict | Trigger | What happens |
|---|---|---|
| `MATCH` | Official NaPTAN name, after normalising case, punctuation and `&` | Nothing to do |
| `ALIAS` | Accepted alias for exactly one station (short form, former name, abbreviation) or a TIPLOC / ATCO code | Correction proposed, reviewer approves |
| `TYPO` | Fuzzy similarity of 92% or more, or a single-character slip in a name of 6+ characters, with no other station within 5 points | Correction proposed, reviewer approves |
| `AMBIGUOUS` | Alias shared by several stations, similarity of 70 to 92%, or several close candidates | Ranked candidates shown, reviewer chooses |
| `UNKNOWN` | Nothing at least 70% similar | Flagged, reviewer investigates |

Four rules make the pipeline safe, and `tests/test_matcher.py` pins each one:

1. **Aliases before fuzzy.** `Allerton` is spelled closer to West Allerton,
   but the alias table records that Allerton station was replaced by
   Liverpool South Parkway in 2006, so that is what the tool proposes.
2. **Shared names stay ambiguous.** City names (`Manchester`), shared short
   forms (`Victoria`) and bracket-stripped names that other stations start
   with (`Ashford`) are never auto-corrected, even when misspelled.
3. **Codes are exact or nothing.** TIPLOC codes such as `MNCRPIC` and
   `MNCRVIC` differ by one or two letters, so codes never take part in
   fuzzy matching. `MNCRPIX` is UNKNOWN, not a guess.
4. **Short names need a person.** A percentage threshold is harsh on short
   names, so a single slip is accepted as a typo only from 6 characters up.
   `Sheffeild` becomes Sheffield; `Leds` goes to review with Leeds ranked first.

## Quickstart

```
pip install -e ".[dev,app]"
python scripts/make_sample_submission.py     # synthetic claims with seeded errors
railvalidator sample_submission.xlsx          # headless report
streamlit run app.py                          # review and commit in the browser
pytest                                        # 58 tests
```

The CLI prints a verdict summary and writes `validation_results.xlsx` with
three sheets: the submission with every cell colour-coded and annotated, a
findings list, and a summary. `--proposed out.xlsx` also writes a workbook
with every single proposed correction applied, and `--fail-on-review` exits
with status 1 when any cell needs attention, so the check can run inside a
data pipeline.

The web app shows each proposal with the submitted value, the correction
and the reason. Tick the ones you accept, choose the right station for each
ambiguous cell (or type an official name), and download a corrected
workbook with a change log recording every edit and its justification.

## Explanations without hallucination

Every explanation is filled in from a template using only catalog data: the
official name, its TIPLOC codes, the alias entry and its recorded source, or
a similarity score. For example:

> 'Sheffeild' differs by one character from the official name 'Sheffield'
> (89% similar); the next closest station, Shenfield, scores 78%.

The tool therefore cannot state anything the reference data does not
contain. An LLM could sit behind `explain()` to smooth the wording, taking
this grounded text as its only input, and the review step would still apply
to every change.

## The data, and what it took to clean it

The catalog is built from the NaPTAN `Stops.csv` export (about 435,000 rows,
100 MB, almost all bus stops) by `scripts/build_catalog.py`. The raw file had
real quality problems, all fixed by rule and all listed in
[`data/build_report.md`](data/build_report.md):

* **2,716 rail records reduce to 2,644 stations.** 44 inactive records are
  dropped, including closed stations and continental destinations such as Paris Nord.
* **25 stations have several records** that describe one station, and are
  merged. Clapham Junction alone has five. Liverpool South Parkway still
  carries the old Allerton code `ALERTN` alongside its own.
* **11 names have non-standard suffixes** (`Railway Station`, `Station`,
  `Halt (Rail Station)`) and are cleaned to match the rest.
* **11 records have no coordinates**, almost all of them Elizabeth line
  entries. Three use a shortened name (`Liverpool Street`, `Paddington`,
  `Abbey Wood`) and are merged into their full-name station, two merge as
  duplicates, and the remaining six are kept and listed.
* Records with the same name are merged only if they are within 2 km of
  each other, so two genuinely different stations can never be combined.

`data/aliases.csv` holds the hand-maintained aliases, and every row records
its source. The loader rejects any alias whose target is not an official
station name, so the alias file cannot drift out of step with the catalog.

To rebuild the catalog from the latest NaPTAN release:

```
python scripts/build_catalog.py --download
```

## Project structure

```
railvalidator/
  normalise.py   comparison keys (case, accents, punctuation, "&")
  catalog.py     NaPTAN cleaning, station model, alias loading and rules
  matcher.py     the tiered validation pipeline
  explain.py     grounded plain-language explanations
  review.py      whole-submission validation and applying decisions
  excel_io.py    submission reader, annotated report and commit workbooks
  cli.py         headless entry point
app.py           Streamlit review-and-commit app
scripts/
  build_catalog.py           raw NaPTAN to data/stations.csv + build report
  make_sample_submission.py  synthetic claims with seeded errors
  make_test_fixture.py       small fixed station extract for the tests
data/
  stations.csv     the cleaned catalog (derived from NaPTAN)
  aliases.csv      hand-maintained aliases with sources
  build_report.md  every data-quality fix made during the build
tests/             58 tests: one per tier, the safety rules, data cleaning,
                   review logic, workbook output and an app smoke test
```

Tests run against `tests/fixtures/stations.csv`, a fixed extract of 68
stations, so they stay fast and never change when NaPTAN is refreshed.
GitHub Actions runs linting, formatting checks and the full test suite on
Python 3.11 and 3.12 for every push.

## Background

The problem shape and the design (tiered matching, alias before fuzzy,
grounded explanations and the review-and-commit workflow) come from a
validation tool I built during a summer internship at National Grid, where
it is used by the Asset Operations team on live procurement submissions.
This repository is a from-scratch reimplementation for my portfolio, moved
to a different domain with openly licensed reference data. No code, data or
formats from the internship are included.

## Licence

Code: MIT, see `LICENSE`. Station data: derived from NaPTAN under the Open
Government Licence v3.0, see `ATTRIBUTION.md`.

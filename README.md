# Bihar Panchayat Election Results, 2016

[![CI](https://github.com/in-rolls/local_elections_bihar/actions/workflows/ci.yml/badge.svg)](https://github.com/in-rolls/local_elections_bihar/actions/workflows/ci.yml)
[![Code license: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)

Candidate information and valid votes from the 2016 Bihar panchayat elections, collected from the [State Election Commission's historical results form](http://sec.bihar.gov.in/ovc.aspx). The repository preserves the original six CSVs and provides typed Parquet exports with source checksums, row provenance, and explicit duplicate links. The current tools operate offline.

## Data

| File | Source office | Records | Later exact copies | Missing candidate names |
|---|---|---:|---:|---:|
| [mukhiya.parquet](data/fin/mukhiya.parquet) | Mukhiya | 96,266 | 0 | 5 |
| [sarpanch.parquet](data/fin/sarpanch.parquet) | Sarpanch | 45,059 | 0 | 3 |
| [ward_member.parquet](data/fin/ward_member.parquet) | Ward Member | 277,219 | 2 | 9 |
| [panch.parquet](data/fin/panch.parquet) | Panch | 136,676 | 640 | 1 |
| [panchayat_samiti_member.parquet](data/fin/panchayat_samiti_member.parquet) | Panchayat Samiti Member | 80,259 | 0 | 3 |
| [zila_parishad_member.parquet](data/fin/zila_parishad_member.parquet) | Zila Parishad Member | 10,126 | 0 | 1 |

There are 645,605 collected rows across the six files. Each file contains labels for 38 districts. These are candidate-record counts, not unique seats, people, or independently verified election totals. Mukhiya and Sarpanch are separate source offices, as are Ward Member and Panch; the converter does not combine them.

Original files remain in [data/](data/). [MANIFEST.json](data/fin/MANIFEST.json) records input/output checksums, schemas, row counts, later duplicate counts, and missing-name counts. [schemas.json](schemas.json) declares the exact columns and office expected for each file. No dataset DOI is recorded in this repository.

## Column dictionary

The source columns remain strings, including age, vote cells, identifiers, and contact fields. Empty cells become null; leading zeroes and original-script text are preserved. Added year and provenance fields are typed explicitly.

| Column | Meaning |
|---|---|
| `year` | int16; 2016, assigned from the documented collection rather than a source CSV column |
| `post` | Source office label |
| `district`, `block`, `panchayat`, `ward` | Source geography; lower-level columns occur only in the applicable files |
| `number` | Source territorial/constituency identifier; it is scoped to its office and geography |
| `reservation_status` | Reservation status of the seat |
| `sr_no` | Candidate serial within the source table |
| `candidate_name`, `father_husband_name` | Candidate and relation-name fields |
| `gender`, `age`, `category`, `educ` | Candidate attributes as supplied by the source |
| `mobile_number`, `address`, `email` | Historical candidate contact fields |
| `valid_vote`, `remarks` | Source valid-vote cell and remarks |
| `source_row` | int32; logical source CSV row, starting at 1 after the header |
| `duplicate_of_source_row` | Nullable int32; first row with exactly the same source-cell values, for later copies |
| `candidate_missing` | bool; candidate name is empty or whitespace-only |

Seat `reservation_status` and candidate `category` are different variables. Neither is inferred from names. `valid_vote` is not recoded from text into a numeric outcome, and `remarks` is not assumed to encode a universally reliable winner flag.

The Mukhiya and Sarpanch files include district, block, and panchayat. Ward Member and Panch add ward. Panchayat Samiti Member includes district and block; Zila Parishad Member includes district. The manifests preserve these differences rather than fabricating unavailable lower-level identifiers.

## Coverage and known gaps

**All source rows are retained.** There are 642 later exact copies: 640 in Panch and two in Ward Member. Their `duplicate_of_source_row` values point to the first copy in that file. This records a reproducible relationship without deciding whether repeated source observations should be removed for a particular analysis. Duplicate tracking continues across output batches.

Twenty-two rows have no usable candidate name. They remain in the export with `candidate_missing=true`. Original whitespace is preserved where present, so the flag can be true even when the raw cell contains spaces.

The historical collectors traversed dropdowns for office, district, block, panchayat, and territorial unit, with different paths for each office. They supported manual resume positions and appended results to CSVs. A complete acquisition manifest and saved raw HTML were not retained. Row counts therefore cannot establish complete coverage or explain every duplicate and omission. Original request times and failed units cannot be reconstructed from the published CSVs alone.

The data do not supply a verified cross-office or cross-election person/seat identifier. Do not treat `number` or `sr_no` as globally unique. Historical contact fields and candidate attributes have not been checked for current accuracy. Later elections are not included.

## How collected

| Stage | Method | Retained evidence |
|---|---|---|
| Enumeration | The SEC results form's office and geographic dropdowns | Source office/geography columns in each CSV |
| Candidate results | Separate ASP.NET form traversal for each of the six offices | Candidate attributes, seat reservation, votes, and remarks |
| Publication | Appended CSV rows from the historical collection | Six original CSV files |
| Parquet export | Offline conversion in batches of 5,000 rows | Typed schemas, source-row provenance, duplicate links, and checksums |

The [historical implementation](https://github.com/in-rolls/local_elections_bihar/tree/1efc650) preserves the six collection scripts. The current environment contains the offline converter and its tests. It makes no requests to the historical SEC form and does not imply that the old form remains available.

## Usage

```sh
git clone https://github.com/in-rolls/local_elections_bihar.git
cd local_elections_bihar
uv sync --frozen --group dev
make verify-data
```

Read a published file:

```python
import pyarrow.parquet as pq

table = pq.read_table("data/fin/mukhiya.parquet")
print(table.num_rows)
print(table.schema)
```

Rebuild the six exports:

```sh
make to-parquet
make verify-data
```

Conversion checks the office label and exact column list, keeps row order, and writes through a temporary file before replacing an export. Verification compares the stored schema and every batch with the original CSV-derived records, then checks the source and output hashes.

## Development

```sh
make check
make ci-docker
```

Checks cover all six schemas, separate candidate/seat categories, leading zeroes, repeated records across batch boundaries, missing names, extra output rows, and interruptions after partial writes. Ruff, formatting, pre-commit, and complete export verification run locally. CI and the standard Docker target test Python 3.12 and 3.14.

## Citation

Gaurav Sood. *Bihar Panchayat Election Candidate Results, 2016*. Include the repository URL and commit used. [CITATION.cff](CITATION.cff) provides machine-readable metadata. Contact: [contact@gsood.com](mailto:contact@gsood.com).

## License

Code is [MIT licensed](LICENSE). The election results were published by the Bihar State Election Commission. No separate data license is asserted in this repository.

## 🔗 Adjacent Repositories

- [in-rolls/local_elections_kerala](https://github.com/in-rolls/local_elections_kerala) — Kerala Local Government Seat Reservation Data and Winner Attributes
- [in-rolls/local_elections_up](https://github.com/in-rolls/local_elections_up) — UP Local Election Data --- GP and ULB. Seat reservation, winner, and candidates for some elections
- [in-rolls/local_elections_uttarakhand](https://github.com/in-rolls/local_elections_uttarakhand) — Data on Local Elections from Uttarakhand
- [in-rolls/ration_bihar](https://github.com/in-rolls/ration_bihar) — Scripts for scraping Ration Card Data From Bihar
- [in-rolls/parse_unsearchable_rolls](https://github.com/in-rolls/parse_unsearchable_rolls) — Parse Unsearchable Electoral Rolls

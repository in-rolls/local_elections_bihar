# Bihar Local Elections

[![CI](https://github.com/in-rolls/local_elections_bihar/actions/workflows/ci.yml/badge.svg)](https://github.com/in-rolls/local_elections_bihar/actions/workflows/ci.yml)
[![Code license: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)

Bihar local-election records from the State Election Commission: six offices in 2016, a statewide mukhiya index from the current 2021–2026 portal, and an explicitly dated 2021 mukhiya pilot in Arwal. Source responses, typed exports, checksums and collection tools are included.

## 2016 data

Candidate information and valid votes collected from the [historical SEC results form](http://sec.bihar.gov.in/ovc.aspx). The original six CSVs are preserved.

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

The data do not supply a verified cross-office or cross-election person/seat identifier. Do not treat `number` or `sr_no` as globally unique. Historical contact fields and candidate attributes have not been checked for current accuracy. The six historical CSVs cover 2016 only; later collections have separate directories.

## How collected

| Stage | Method | Retained evidence |
|---|---|---|
| Enumeration | The SEC results form's office and geographic dropdowns | Source office/geography columns in each CSV |
| Candidate results | Separate ASP.NET form traversal for each of the six offices | Candidate attributes, seat reservation, votes, and remarks |
| Publication | Appended CSV rows from the historical collection | Six original CSV files |
| Parquet export | Offline conversion in batches of 5,000 rows | Typed schemas, source-row provenance, duplicate links, and checksums |

The [historical implementation](https://github.com/in-rolls/local_elections_bihar/tree/1efc650) preserves the six collection scripts. The offline converter makes no requests to the historical SEC form. Later collections use the current portal and separate scripts.

## 2021 and the current portal

| Collection | Coverage | Records | Files |
|---|---|---:|---|
| Current mukhiya winner index | All 38 districts and 533 blocks listed by the portal | 8,067 winners | [Winners](data/fin/portal_2021_2026/winners.parquet), [seat reservations](data/fin/portal_2021_2026/reservations.parquet), [manifest](data/fin/portal_2021_2026/MANIFEST.json) |
| Explicit 2021 mukhiya pilot | Arwal: 5 blocks, 64 panchayats | 559 candidacies, 64 winners | [Candidate lists and results](data/fin/2021/mukhiya_2021.parquet), [manifest](data/fin/2021/MANIFEST.json) |

Sources: SEC [winning candidates](https://sec25.bihar.gov.in/sec_new/Panchayat/WinningCandidates), [seat reservations](https://sec25.bihar.gov.in/sec_new/Panchayat/Reservation), [contesting candidates](https://sec25.bihar.gov.in/sec_new/Panchayat/ContestingCandidates), and [results](https://sec25.bihar.gov.in/sec_new/Panchayat/Result). Responses were collected on September 10, 2026. The statewide collection completed 533 winner requests and 533 reservation requests; it covers the portal's listed blocks, not an independently verified historical census of seats.

**The statewide index has no election-year field.** Its `year` is null: the portal covers the 2021–2026 term and later by-elections. The Arwal pilot explicitly requests phase `2021_1`, displayed by the source as `2021`. Its 1,118 rows comprise 559 candidate-list records and 559 result records, distinguished by `kind`. They are not 1,118 candidacies. Each of the 64 panchayats has one recorded winner.

**Education is in linked documents.** The structured feeds provide age and gender, but no education field. The statewide index includes 8,066 affidavit links. An inspected [2021 affidavit, page 14](https://sec2021.bihar.gov.in/ForPublicPDF_P/Documents1n2/NominationDoc/20210913143841096.pdf#page=14) contains a handwritten candidate biography with educational qualifications, profession and prior elected office; page 10 contains criminal-case declarations. Education and experience have not been extracted or analyzed from these scans.

### Fields and handling

- `district_id`, `block_id`, `post_id` and `panchayat_id` locate records. Candidate serials are scoped to election, office and full geography. IDs from different elections are not assumed to identify the same seat.
- Winner exports retain `candidate_age`, `candidate_gender`, `candidate_category`, affidavit/photo URLs and source geography. `reservation_for_reported` and `reservation_status_reported` are fields from the winner feed; `seat_reservation` comes from the separate reservation feed. These fields are not interchangeable: the first Arwal block already contains a disagreement between the two feeds' caste-reservation labels.
- The 2021 file keeps candidate lists and results separately. Candidate lists carry age, gender and document links; results carry votes and `elected`. All 559 geographic/serial keys occur once in each feed. After whitespace normalization, 91 pairs have different name text, including the source's winner suffix and numbered names. No name-based merge is imposed.
- `source_url`, `fetched_at`, `source_sha256`, `source_row` and `raw_cell` trace each exported row to the saved response. Source cells remain unchanged in `raw_cell`; typed columns facilitate analysis. Schemas and hashes accompany the exports.
- [Raw responses](data/raw/portal_2021_2026) are gzipped request ledgers with HTTP status, UTC time and the original response bytes encoded as base64. The geographic frame retains district/block/office paths. A completed checkpoint is reused; missing or truncated checkpoints are fetched again. HTML error pages are rejected rather than counted as empty results.

Collection uses three HTTP sessions. A nine-request pilot took 3.8 seconds with three sessions; three sequential requests took 3.1 seconds. The statewide mukhiya job requires 1,066 data requests plus frame enumeration. District-only and all-office requests returned no records in reconnaissance, so collection follows the working office/block request pattern.

```sh
uv run python scripts/sec_portal.py list
caffeinate -dims uv run python scripts/sec_portal.py fetch --posts 3
uv run python scripts/sec_portal.py parse
caffeinate -dims uv run python scripts/sec_2021.py fetch --districts 33
uv run python scripts/sec_2021.py parse
```

Omit `caffeinate -dims` outside macOS. The generic collector accepts post IDs 1–6: ward member, panch, mukhiya, sarpanch, panchayat samiti member and zila parishad member. The published current-portal collection is mukhiya only. Use `--districts` to restrict collection and `--workers` to set concurrency. Parsing is offline and can be rerun against the saved responses.

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

Gaurav Sood. *Bihar Local Elections*. Include the repository URL and commit used. [CITATION.cff](CITATION.cff) provides machine-readable metadata. Contact: [contact@gsood.com](mailto:contact@gsood.com).

## License

Code is [MIT licensed](LICENSE). The election results were published by the Bihar State Election Commission. No separate data license is asserted in this repository.

## 🔗 Adjacent Repositories

- [in-rolls/local_elections_kerala](https://github.com/in-rolls/local_elections_kerala) — Kerala Local Government Seat Reservation Data and Winner Attributes
- [in-rolls/local_elections_up](https://github.com/in-rolls/local_elections_up) — UP Local Election Data --- GP and ULB. Seat reservation, winner, and candidates for some elections
- [in-rolls/local_elections_uttarakhand](https://github.com/in-rolls/local_elections_uttarakhand) — Data on Local Elections from Uttarakhand
- [in-rolls/ration_bihar](https://github.com/in-rolls/ration_bihar) — Scripts for scraping Ration Card Data From Bihar
- [in-rolls/parse_unsearchable_rolls](https://github.com/in-rolls/parse_unsearchable_rolls) — Parse Unsearchable Electoral Rolls

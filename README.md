# Bihar Local Elections

[![CI](https://github.com/in-rolls/local_elections_bihar/actions/workflows/ci.yml/badge.svg)](https://github.com/in-rolls/local_elections_bihar/actions/workflows/ci.yml)
[![Code license: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)

Bihar local-election records from the State Election Commission: six offices in 2016, a statewide mukhiya index from the current 2021–2026 portal, and statewide candidate lists and results explicitly dated 2021. Source responses, typed exports, checksums and collection tools are included.

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
| Explicit 2021 mukhiya election | 38 districts, 533 blocks, 8,067 enumerated panchayats | 66,430 candidacies; 66,392 result records; 8,050 flagged winners | [Candidates](data/release/2021/gp_head_candidates_2021.parquet), [winners](data/release/2021/gp_head_winner_records_2021.parquet), [coverage](data/release/2021/coverage.parquet), [validation](data/release/2021/validation.json) |
| 2021 winner qualifications | All 64 Arwal winners inspected | Degree status classified for 57; unresolved for 7 | [CSV](data/fin/2021/education.csv), [Parquet](data/fin/2021/education.parquet), [transcriptions](data/fin/2021/education_review.csv), [sources and checksums](data/fin/2021/education.json) |

Sources: SEC [winning candidates](https://sec25.bihar.gov.in/sec_new/Panchayat/WinningCandidates), [seat reservations](https://sec25.bihar.gov.in/sec_new/Panchayat/Reservation), [contesting candidates](https://sec25.bihar.gov.in/sec_new/Panchayat/ContestingCandidates), and [results](https://sec25.bihar.gov.in/sec_new/Panchayat/Result). Responses were collected on September 10, 2026. The statewide collection completed 533 winner requests and 533 reservation requests; it covers the portal's listed blocks, not an independently verified historical census of seats.

**The statewide index has no election-year field.** Its `year` is null: the portal covers the 2021–2026 term and later by-elections. The separate statewide 2021 release requests phase `2021_1`, displayed as `2021`. All 66,392 result keys match candidate-list keys; 38 candidacies have no result record. Of 8,067 enumerated panchayats, 8,050 have one flagged winner, eight have results without a winner flag, and nine return empty results. All remain in the [coverage table](data/release/2021/coverage.parquet). The frame was retrieved in 2026; it is not an independent census of seats as constituted in 2021.

**Reservation checks:** the [SEC’s 2021 report](https://sec.bihar.gov.in/PanchayatRpt/ch1.aspx) and the saved feed both contain 8,067 mukhiya seats, including 3,583 women-reserved seats. The feed has one more SC seat and one fewer BC seat. All 8,050 dated winners join by district, block and panchayat IDs. In women-reserved seats, 35 winners are coded male in the 2021 candidate feed; the current winner feed codes 31 of these as female. These are unresolved source conflicts. Matching totals do not verify individual assignments. [Checks](data/fin/reservation_check_2021/validation.json), [flagged records](data/fin/reservation_check_2021/flagged_winners.parquet), [source hashes and schema](data/fin/reservation_check_2021/MANIFEST.json), and [offline audit](scripts/check_reservations_2021.py).

**Education has been transcribed for 64 Arwal winners.** All 64 winners were linked to candidate lists using district, block, panchayat and candidate serial, then their downloaded nomination PDFs were inspected. [The export](data/fin/2021/education.csv) retains the reported qualification, degree and literacy indicators, prior elected office, document reservation text, source URL, page number and PDF hash. [Inspected pages](data/fin/2021/education_pages) accompany the transcriptions.

Degree status is unresolved for seven winners: two documents lack the candidate's education page, one names a school without a qualification, one says only “EDUCATED,” and three have ambiguous qualification text. Unknowns remain null. Reservation is classified from document text for 51 winners; 13 remain unspecified. Of the 25 document-classified women's reserved seats, 21 have classified degree status; the corresponding counts are 24 of 26 open seats and 12 of 13 seats with unspecified reservation. These are extraction counts, not reservation-effect estimates. [Coverage and provenance](data/fin/2021/education.json).

Codex visually transcribed these records; there has been no independent second coding. Tesseract locates likely pages but does not assign qualifications. Candidate and proposer biographies are distinguished. Qualifications are self-reported, and a blank field is not evidence of illiteracy. These transcriptions cover Arwal. Statewide affidavit collection and extraction were stopped at the owner’s request. The public winner table and 2021 candidate-detail page checked for Awgila contain no structured education field; statewide 2021 education remains unavailable in this release.

<details>
<summary>Inspect a qualification declaration</summary>

Rajanti Devi's candidate biography reports “इंटर पास” (intermediate passed). The seat-reservation field reads “सामान्य महिला.” [Original PDF, page 12](https://sec2021.bihar.gov.in/ForPublicPDF_P/Documents1n2/NominationDoc/20210909141417391.pdf#page=12).

<img src="data/fin/2021/education_pages/33_1_330010011_4_p12.png" alt="Candidate biography showing the education and seat-reservation fields" width="500">

</details>

### Fields and handling

- `district_id`, `block_id`, `post_id` and `panchayat_id` locate records. Candidate serials are scoped to election, office and full geography. IDs from different elections are not assumed to identify the same seat.
- Winner exports retain `candidate_age`, `candidate_gender`, `candidate_category`, affidavit/photo URLs and source geography. `reservation_for_reported` and `reservation_status_reported` are fields from the winner feed; `seat_reservation` comes from the separate reservation feed. These fields are not interchangeable: the first Arwal block already contains a disagreement between the two feeds' caste-reservation labels.
- The 2021 file keeps candidate lists and results separately. Candidate lists carry age, gender and document links; results carry votes and `elected`. All geographic/serial keys are unique within each feed. All 8,050 winner keys match candidate lists, but 242 winner names differ literally after removing the winner suffix and surrounding whitespace. The differing names remain available; no name-based merge is imposed.
- `source_url`, `fetched_at`, `source_sha256`, `source_row` and `raw_cell` trace each exported row to the saved response. Source cells remain unchanged in `raw_cell`; typed columns facilitate analysis. Schemas and hashes accompany the exports.
- [Raw responses](data/raw/portal_2021_2026) are gzipped request ledgers with HTTP status, UTC time and the original response bytes encoded as base64. The geographic frame retains district/block/office paths. A completed checkpoint is reused; missing or truncated checkpoints are fetched again. HTML error pages are rejected rather than counted as empty results.

Collection uses three HTTP sessions. A nine-request pilot took 3.8 seconds with three sessions; three sequential requests took 3.1 seconds. The statewide mukhiya job requires 1,066 data requests plus frame enumeration. District-only and all-office requests returned no records in reconnaissance, so collection follows the working office/block request pattern.

```sh
uv run python scripts/sec_portal.py list
caffeinate -dims uv run python scripts/sec_portal.py fetch --posts 3
uv run python scripts/sec_portal.py parse
./crawl.sh
```

Omit `caffeinate -dims` outside macOS. The generic collector accepts post IDs 1–6: ward member, panch, mukhiya, sarpanch, panchayat samiti member and zila parishad member. The published current-portal collection is mukhiya only. Use `--districts` to restrict collection and `--workers` to set concurrency. Parsing is offline and can be rerun against the saved responses.

### State release and central import

The [central repository](https://github.com/in-rolls/local_reservations) contract assigns collection, parsing and corrections to this repository. `local_reservations` imports the versioned state release through its Bihar adapter; `quota_elite_quality` consumes the harmonized data for analysis. The central adapter pins the 2021 table hashes and checks row counts, schemas, unique keys and winner/coverage reconciliation. The six 2016 inputs retain their existing paths.

The 2021 release includes an explicit [schema](data/release/2021/SCHEMA.json), [dictionary](data/release/2021/dictionary.csv), [checksums](data/release/2021/CHECKSUMS), and [manifest](data/release/2021/MANIFEST.json) linking rows to saved SEC responses. Candidate and result observations retain separate source URLs, hashes and row locators. Missing results remain null. The undated current reservation feed is excluded from this release.

Restore the complete [raw-response archive](data/raw/statewide_2021.tar.gz), then rebuild offline:

```sh
mkdir -p data/raw/statewide_2021
tar -xzf data/raw/statewide_2021.tar.gz -C data/raw/statewide_2021
make release-data
make verify-2021
```

[Archive metadata](data/raw/statewide_2021_archive.json) records its checksum. `./crawl.sh` resumes collection and downloads every flagged winner's affidavit if explicitly restarted; acquisition is currently stopped. PDFs are checked for a PDF signature, readable page count and SHA-256; failures are retained and retried on resume. The download stops before consuming the final 5 GiB of disk space. Live progress is saved to `data/interim/2021/download_status.parquet`, with one row for every requested winner, and a matching JSON summary. PDF bytes remain local during acquisition; the response archive and released tables are published.

Rebuild the reservation source checks offline with `uv run python scripts/check_reservations_2021.py`.

### Rebuild qualifications

Install Poppler (`pdfinfo`, `pdftoppm`, `pdftotext`) and Tesseract with English and Hindi language data. On macOS, `brew install poppler tesseract tesseract-lang` supplies these tools; Ubuntu uses `poppler-utils tesseract-ocr tesseract-ocr-hin`.

```sh
uv run python scripts/affidavits.py frame
caffeinate -dims uv run python scripts/affidavits.py download
caffeinate -dims uv run python scripts/affidavits.py locate
uv run python scripts/affidavits.py export
```

Download and page-location stages resume from `data/derived/affidavits_2021/`. Export combines the checked-in review CSV with downloaded document metadata and page images. It rejects duplicate or missing review keys, invalid binary codes, mismatched source hashes, and pages outside the document. The review CSV is the visual-transcription input; OCR alone cannot regenerate it. `graduate_plus=1` means a reported completed degree, `0` a reported lower qualification, and null an unresolved level. `illiterate` and `prior_elected` likewise preserve unknowns. `quota_document` records women's seat reservation from the document, independently of candidate gender; it is not an official reservation-roll validation.

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

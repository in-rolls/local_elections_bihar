# Gaya Mukhiya, 2011: supporting source transcriptions

For the main 2011 winner data, use
[`mukhiya_reports/winner_records.parquet`](../mukhiya_reports/winner_records.parquet).
It already includes Gaya's 338 PDF winner records.

The workbook supplies GP and block labels directly. The runner-up file now links
GP labels from the companion winner PDF using the checked alignment described
below. Both published files require a nonblank person name, district, block and
GP. A printed report serial identifies a source row, not an official seat.

The workbook explicitly identifies the 2011 election. The maintainer also
confirmed the PDF collection as 2011, noting its “पूर्व निर्वाचित” columns for
prior elected office in 2001 and 2006. All three tables use `election_year=2011`;
the [source provenance](../../PROVENANCE.md) records that evidence.
Extracted workbook/PDF name differences still require checking against the
originals. Keep the source records separate until that review resolves them.
These files do not yet establish a reconciled roster or complete seat frame.

| File | Rows | One row represents |
| --- | ---: | --- |
| `spreadsheet_winner_records.parquet` | 330 | A reported winner with GP and block from `Gaya.xls` |
| `pdf_winner_records.parquet` | 338 | A reported winner from the Gaya PDF; already included in the main 2011 file |
| `runner_up_records.parquet` | 337 | A runner-up with GP inferred from the companion winner PDF; `seat_link_basis` records this |
| `runner_spreadsheet_conflicts.csv` | 40 | A name/block comparison pair: 38 distinct runner records matched to workbook winners |

The winner tables include names, geography labels, age, education, occupation,
reported annual income, and children. The PDF also reports gender, reservation,
candidate category, relatives and previous offices. No vote totals, vote shares,
margins or inferred demographic classifications are supplied. Runner records
include names, block, reservation text, linked GP and references to both PDFs.

## Recovering the runner-up seats

The runner-up PDF prints a GP name only at each block heading. Its rows span
different reservation labels, so that heading cannot supply the GP for every
person below it. Residential villages are not treated as GP names.

The companion winner PDF prints a GP on each row. All **338 source rows** align
one-to-one between the two PDFs on serial, block and exact reservation text,
including spelling quirks. All **25 block-first GP headings** also agree. The
parser requires the entire alignment to pass before linking any GP labels; a
missing or repeated serial, differing block/reservation, or disagreeing GP
heading stops parsing. Headers at page ends are carried to the first following
row for this check.

This is an **inference from paired report ordering**, not a printed seat code or
independent verification of each pairing. `seat_link_basis` records that fact.
`seat_source_file`, `seat_source_sha256`, `seat_source_page` and
`seat_source_record_id` locate the companion evidence. The GP is not copied from
the workbook or inferred from a person's name. Repeated GP labels in the winner
PDF remain repeated; this linkage does not establish unique official seats.

One runner source row has a blank name (serial 107, Imamganj, linked GP मंझौली),
and one workbook row has a blank winner name (Sheet1 row 94, Wazirganj, GP विच्छा).
They are excluded from the person tables, leaving 337 runners and 330 workbook
winners. Their identifiers and exclusion reasons are recorded in the existing
manifest. The originals retain both rows. The workbook has no repeated
block–GP combination.

## Extracted differences to review

Only **56 of 338** PDF winner records have a unique normalized name match within
block in the workbook; one has multiple matches and 281 have none. Names alone
do not establish identity or the same seat. Some workbook winners instead match
runner-up names: 38 runner records produce 40 comparison pairs. These observations
require checking the extraction, column meanings and record matching against
the originals. They do not establish which reading is correct or whether a
particular name pair represents the same person.

The alternate winner PDF agrees with the primary on all 338 serial/name/block
combinations, but has **370 differing field values**. The 56 unique workbook
comparisons have **193 differing field values**. Differences are preserved in
`issues.csv`; no alternate values silently replace primary cells.

There are 25 primary rows sharing a literal block/panchayat label with another
row, and 16 sharing a name within block. Nagar has 32 records, including repeated
names with different details. All source rows are retained and flagged. Neither
source serials nor `record_id` are seat or person identifiers.

`coverage.csv` reconciles all 338 PDF records with the companion summary by
printed block label. It retains zero-count summary labels and the separate
Vajirganj/Wazirganj labels. The explicit Hindi crosswalk in
[`parse_gaya.py`](../../../scripts/year2011/parse_gaya.py) maps these two to the same block;
there are 24 distinct mapped blocks. This agreement tests extraction coverage,
not the correctness of the report, its year or its population coverage.

## Reading and interpreting the data

```python
import pyarrow.parquet as pq

winners = pq.read_table("data/2011/gaya_mukhiya/spreadsheet_winner_records.parquet")
print(winners.select(["block", "panchayat_raw", "candidate_name", "age"]).to_pandas())
```

`MANIFEST.json` documents each table's columns, types, null counts and blank
counts. Source strings and their typed
counterparts provide a row-level recode record. The rules are:

- Decode legacy font encodings to Unicode, normalize to NFC, collapse whitespace
  and preserve spelling and honorifics. `_raw` means decoded, otherwise unrecoded
  source text, not the original font bytes. Original files remain authoritative.
- Convert digit-only age, annual income and child-count cells to integers.
  Preserve zero; blank or nonnumeric values become null in typed columns.
  Treat ages outside 18–120 as invalid, preserve their source values and log them.
  This broad plausibility rule is not a legal eligibility classification.
- Six PDF ages are invalid: 0, 0, 1980, 1972, 1966 and 15. Do not convert apparent
  birth years to ages without a verified election year. PDF typed age has six
  missing values; published workbook typed age has 12.
- Map the printed gender labels महिला/महीला to `female` and पुरुष/पुरूष to `male`.
  One blank label remains null. Printed labels are retained even when a name might
  suggest otherwise. Workbook gender is unavailable and is not inferred.
- `reservation_women` is true only for an explicit महिला in the reservation cell;
  otherwise it is null. Candidate category and seat reservation remain separate.
- Income currency is not explicit in the heading. Retain reported amounts without
  currency conversion. The PDF maximum is 4,000,000; it has not been independently
  corroborated. Other typed PDF ranges are age 22–67, sons 0–6, daughters 0–8.
- Blank previous-office entries are unknown, not evidence of no previous office.

The cross-source comparison keeps the primary PDF's 338-row universe. Alternate
comparison requires the same serial, block and literal decoded name. Workbook
comparison uses mapped block plus name with leading श्रीमती/श्री/सुश्री,
whitespace, periods and Devanagari abbreviation zero removed. This normalization
is confined to comparison keys. Only unique workbook matches receive a row link;
ambiguous and unmatched records remain in the output. No fuzzy join or geography
imputation is performed. The runner comparison instead emits all matching pairs
and explicitly does not establish a seat match.

## Sources and receipts

Originals reside in `/Volumes/Staging/local_elections_bihar/2011/raw/central_handoff/`,
exposed locally through `data/2011/raw/central_handoff/`. The handoff originates in
`in-rolls/local_elections` at commit `fa4c4e79`; see the [data guide](../../README.md)
for source storage and availability. The source files are:

| Role | Path within `central_handoff/` | Locator |
| --- | --- | --- |
| Primary winners | `winners/GAYA/GAYA_GPM.pdf` | 26 pages, source serials 1–338 |
| Alternate winners | `alternate_winners/GAYA/GAYA_GPM.pdf` | 26 pages, source serials 1–338 |
| Dated workbook | `mukhiya_spreadsheets/Gaya.xls` | Sheet1, heading “पंचायत आम निर्वाचन, 2011” |
| Runner names | `runners/GAYA/GAYA_gpm.pdf` | 16 pages, source serials 1–338 |
| Summary | `summaries/alternate_winners/GAYA/GAYA_WMFcount_on_post.pdf` | 8 pages |

Every parsed record identifies its source file and SHA-256, plus a PDF page or
workbook row. Primary PDF records also include their bounding box. Alternate
comparisons use the same serial; summary page references appear in `coverage.csv`.
`MANIFEST.json` pins the five original files, parser code, mappings, reviewed
sample and dependency lock. The same manifest records output hashes, reconciliation and issue counts.

The PDF text uses embedded glyph encodings whose original Unicode maps scramble
Hindi. `font_map.json` maps reviewed glyphs, keyed by the embedded font's
SHA-256. `hindi.py` repairs text maps in memory and restores short-i and reph
ordering. It preserves PDF drawing order within cells. Header column boundaries
recover last rows where truncated table rules otherwise merge cells. Summary
parsing carries block headers across page breaks. No OCR is used.

The committed glyph map is sufficient for normal parsing. For its derivation,
`map_fonts.py` records exact outline matching, GSUB decomposition and reviewed
contextual glyph overrides. Re-derivation requires the specific SHA-pinned Arial
Unicode reference font, which is proprietary and not redistributed. It also reads
`alternate_winners/GAYA/GAYA_w_count.pdf` to map its summary font. For example:

```sh
uv run python -m scripts.year2011.map_fonts \
  --font '/System/Library/Fonts/Supplemental/Arial Unicode.ttf' \
  --out /tmp/gaya-font-map.json
```

Workbook text is decoded only in cells marked Kruti Dev 010. The ordered mapping
comes from the MIT-licensed
[Kruti Dev converter](https://github.com/ravitaak/krutidevtounicode/blob/main/lib/src/krutidevtounicode.dart),
with an explicit local correction for चौ. Attribution and the license are in
the repository [LICENSE](../../../LICENSE); the exact mapping is committed.

## Validation and reproduction

A 32-record visual transcription from original primary PDF pages 1, 10, 18 and 26
is stored in [`gaya_visual_review.csv`](../../../tests/fixtures/2011/gaya_visual_review.csv).
Names, ages, gender labels and incomes agree with those reviewed records. This was
an assistant visual review, not independent human labeling or a random accuracy
study. It covers selected PDF fields; workbook decoding and the remaining PDF
fields have not received an equivalent independent transcription review.

The regression tests exercise mark ordering, the corrected Kruti spelling,
truncated last-row rules, block continuation, source-year separation, the visual
sample and a complete local parse when originals are available.

With the raw files mounted at the paths above:

```sh
uv sync --frozen --group dev
make parse-2011
uv run pytest -q tests/test_parse_2011.py
```

An alternate source location can be supplied with `--raw` and an output directory
with `--out`. Parsing writes the final tables and receipts only. It does not copy
originals or save rendered pages or intermediate PDFs. A public raw-data download
has not yet been arranged. Affidavits are outside this pilot.

The [repository scope](../../../README.md#scope-and-collection-priorities) makes
seat reservations, candidates and winners the next extraction priorities for
all six panchayat offices. Turnout and indirect-leadership rosters are deferred.
The current winner-only workbook does not establish all-candidate coverage or a
reservation-linked seat frame.

Review the workbook transcription against a rendering with the original Kruti
font and compare the apparent name differences directly with the PDFs. The year
assignment does not settle those extraction and matching questions. District
Mukhiya extraction is available separately; the five other offices remain to be
parsed.

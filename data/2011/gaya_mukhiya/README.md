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
prior elected office in 2001 and 2006. Both tables use `election_year=2011`;
the [source provenance](../../PROVENANCE.json) records that evidence.
Extracted workbook/PDF name differences still require checking against the
originals. Keep the source records separate until that review resolves them.
These files do not yet establish a reconciled roster or complete seat frame.

| File | Rows | One row represents |
| --- | ---: | --- |
| `spreadsheet_winner_records.parquet` | 330 | A reported winner with GP and block from `Gaya.xls` |
| `runner_up_records.parquet` | 337 | A runner-up with GP inferred from the companion winner PDF; `seat_link_basis` records this |

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

Workbook and PDF name differences still need review against the originals.
They are separate source claims; they do not establish contradictory election
outcomes. The district table retains repeated literal GP labels with flags.

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
- Runner reservation text is preserved without assigning a category. See the
  district winner table for its conservative reservation recodes.
- Income currency is not explicit in the heading. Retain reported amounts without
  currency conversion. The PDF maximum is 4,000,000; it has not been independently
  corroborated. Other typed PDF ranges are age 22–67, sons 0–6, daughters 0–8.
- Blank previous-office entries are unknown, not evidence of no previous office.

## Original sources

Paths are relative to `data/2011/raw/reports/`:

| Role | Original file |
| --- | --- |
| Winner PDF supplying runner seat labels | `winners/GAYA/GAYA_GPM.pdf` |
| Dated winner workbook | `mukhiya_spreadsheets/Gaya.xls` |
| Runner-up PDF | `runners/GAYA/GAYA_gpm.pdf` |

`MANIFEST.json` pins these three originals, the parser, character mappings and
published outputs. Every record identifies its original SHA-256 and PDF page or
workbook row. Runner records link to `mukhiya_reports/winner_records.parquet`;
the Gaya PDF winners are published only in that district table. Alternate reports
and summary PDFs are preserved separately as unprocessed material and are not
required by this pipeline.

The PDF text uses embedded glyph encodings whose original Unicode maps scramble
Hindi. `font_map.json` maps reviewed glyphs, keyed by the embedded font's
SHA-256. `hindi.py` repairs text maps in memory and restores short-i and reph
ordering. It preserves PDF drawing order within cells. Header column boundaries
recover last rows where truncated table rules otherwise merge cells. No OCR is used.

The committed glyph map is sufficient for normal parsing. For its derivation,
`map_fonts.py` records exact outline matching, GSUB decomposition and reviewed
contextual glyph overrides. Re-derivation requires the specific SHA-pinned Arial
Unicode reference font, which is proprietary and not redistributed. For example:

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
truncated last-row rules, source-year assignment, the visual
sample and a complete local parse when originals are available.

With the originals at the paths above:

```sh
uv sync --frozen --group dev
make parse-2011
uv run pytest -q tests/test_parse_2011.py
```

An alternate source location can be supplied with `--raw` and an output directory
with `--out`. Parsing writes the final tables and receipts only. It does not copy
originals or save rendered pages or intermediate PDFs. Run
`make fetch-sources YEAR=2011` to restore the originals from Zenodo; see the
[data guide](../../README.md#reproduce-a-dataset). Affidavits are outside this pipeline.

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

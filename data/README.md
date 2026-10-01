# Working with Bihar election data

The [repository scope](../README.md#scope-and-collection-priorities) defines the
collection target: seats and reservations linked to candidates and winners,
across all recoverable general elections and by-elections for six panchayat
offices. Turnout, polling logistics, municipalities, indirect leadership and
further affidavit work are deferred. Existing deferred assets are retained
separately; their presence is not a collection priority.

Start with the published tables in `data/2016/` and `data/2021/`. You do not need
an external drive or the raw collection to use those tables. `make verify` checks
their schemas, row counts, checksums and joins without contacting the SEC.

## One layout, on any disk

```text
data/
  coverage.csv                election/office coverage from parsed tables
  coverage.json               coverage definitions, limitations and source hashes
  CATALOG.csv                 asset counts and sizes, generated from receipts
  SIZE_REPORT.json            year totals, archive sizes, deferred-work sizes
  MIGRATION.csv.gz            original organization receipt, preserved unchanged
  PRUNING.csv.gz              removed paths, SHA-256 and reasons
  provenance/                 original handoff manifest and Zenodo verification
  2006/raw/                   workbooks explicitly headed 2006
  2011/raw/                   winner, runner-up, summary and alternate reports
  undated/raw/                records whose election year remains unresolved
  2016/
    raw/                     source collection and acquisition metadata
    interim/                 small publication receipts; disposable caches when needed
    *.parquet                published tables
    MANIFEST.json            published table checksums and build provenance
  2021/
    raw/                     source collection and acquisition metadata
    interim/                 small publication receipts; disposable caches when needed
    *.parquet                published tables
    affidavits/              existing 64-winner transcription and review inputs
    reservation_check/       published reservation comparison
```

Each year has the same `raw/` and `interim/` structure, including years with empty
working directories. Sources retain their original bytes. Acquisition bundles
include the enumeration frames and request receipts saved alongside responses.
Collection dates are distinct from election years: the 2026 portal snapshot of
the 2021 term is under `2021/raw/portal_snapshot_2026/`. By-election rounds retain
their original phase identifiers within the 2021-term acquisition bundle.

On the maintainer's machine, the physical source and working directories live
under `/Volumes/Staging/local_elections_bihar/<year>/`. The repository's
`data/<year>/raw` and `data/<year>/interim` entries are ignored symlinks to those
directories. Published tables and receipts remain ordinary repository files.
There are no alternative old-path aliases. An unmounted drive makes the source
links unavailable; it does not prevent using or verifying the published tables.

Other users can restore ordinary directories directly under `data/<year>/`, or
use their own storage root. For example, from the repository root:

```sh
mkdir -p /your/storage/bihar/2016/raw /your/storage/bihar/2016/interim
ln -s /your/storage/bihar/2016/raw data/2016/raw
ln -s /your/storage/bihar/2016/interim data/2016/interim
```

Use either ordinary directories or symlinks at these paths; do not replace an
existing directory with a link. Scripts use repository-relative paths and do not
require `/Volumes/Staging`. Their `--raw`, `--frame`, `--results`, and `--out`
options support explicit locations where applicable.

## Measuring collection progress

Run `make coverage` to summarize the existing Parquet tables without downloading
or reparsing originals. [coverage.csv](coverage.csv) counts known frame seats,
reservation labels, seats with candidates and winners, candidate records and
votes, and source-flagged versus derived winners by election and office.
[coverage.json](coverage.json) defines the columns and pins the inputs and parser.
Use it to identify missing records and links; file volume is not a coverage measure.

Election-specific reservation labels and undated term-snapshot labels occupy
different columns. Their presence is not independent validation. Ambiguous seat
codes are excluded from counts of successfully linked candidate/winner seats but
remain in frame and record totals. Provisional 2011 lists report source-record
counts, leaving unique-seat and all-candidate coverage unknown. Other historical
sources remain unparsed. Links across general-election frames remain outstanding.

## Inventory and provenance

The source and working collection is now **7.31 GB**, down from 15.10 GB.
Pruning removed **7.80 GB** of duplicate packaging, export copies, progress logs
and superseded generated tables. A prior organization pass had already removed
4.93 GB of identical archive copies. These savings are separate.

Of the remaining collection, **3.87 GB is core election material**:

| Material | Size | Why retain it |
| --- | ---: | --- |
| Gzipped SEC request/response logs | 3.463 GB | Original HTML/JSON responses and acquisition receipts |
| Earlier 2016 CSV collection | 187.7 MB | Independent historical snapshot for comparison |
| PDFs: 2011 reports and 2016 reservation rosters | 139.6 MB | Original documents |
| Excel workbooks: 2006, 2011 and unresolved years | 62.5 MB | Original handoff sources |
| Frame indexes, metadata and receipts | 13.9 MB | Small indexes needed by current readers and provenance |

The other **3.44 GB** is affidavit and associated research work, including its
existing intermediate files; this was left untouched. This total includes the
3.25 GB affidavit source directory, OCR caches, download state and related inputs.
Published tables and repository provenance files are outside these totals.
Sizes mean file bytes, not disk allocation.

No election source was discarded merely because a generated table exists.
Every non-Mac-metadata member of the removed archives checksum-matched a retained
raw file. The 2021 tars alone contained 1.65 GB of headers, padding and Mac
metadata. The 48 Zenodo chunks were another copy of the 2016 results archive.
The scripts now read retained source directories directly. They do not recreate
those archives during normal collection. Generated reservation tables can be
made on demand from the retained PDFs.

`CATALOG.csv` and `SIZE_REPORT.json` are generated by `make data-summary` from
`MIGRATION.csv.gz` minus `PRUNING.csv.gz`. The former preserves every original
location, canonical path, byte count, SHA-256 and year evidence. The latter
records every removed file, its checksum and the reason for removal.
`provenance/archive_overlap.json` records archive-member comparisons;
`provenance/pruning.json` records the before/after totals.
`repository/` and `storage/` in the original receipt denote the checkout and
external store before organization. This inventory is a dated snapshot, not an
automatically changing index of later acquisitions.

```sh
make data-summary
make data-verify
uv run python scripts/data_inventory.py verify --year 2011 --role raw
```

The local checks and offline rebuild comparisons are recorded in
[`provenance/validation.json`](provenance/validation.json), with the test and
container logs beside it.

Verification checks retained files after applying the pruning receipt; it does not silently
reindex changed inputs or claim that newly collected files were part of the
migration. Run it with the external drive mounted, or against a complete restored
collection. A partial restore should use the matching year/role selection.
The catalog's availability column describes the local layout, not a promised
remote download. The separately verified 2016 Zenodo deposit is described below.

Historical manifests, request ledgers and export instructions are preserved
verbatim, including their original paths and dates. Use the migration receipt to
resolve old paths; `provenance/organization.json` records the former directory
symlinks. Published build manifests retain the code hashes of the build
that produced those artifacts; organization validation is recorded separately.
The reservation-check manifest was regenerated after its path change; its
published results are unchanged.

The older central handoff originates at `in-rolls/local_elections`, commit
`fa4c4e79`, and its original checksum manifest is retained in `provenance/`.
All 32 other-office workbooks have 2006 headings. The `Mukhiya_2006` folder name
is unreliable: Gaya's first row explicitly states 2011, while the first 12 rows
of the other 37 workbooks do not establish their year. Those 37 files and all
35 Sarpanch workbooks remain `undated`. This is a year-classification limit,
not a claim that the records have no recoverable date.

The 2011 PDF collection has winner lists for 23 district folders, alternate
winner reports for eight districts, runner-up reports for eight districts, and
summary/indirect-election reports. The maintainer confirmed the collection as
2011 after reviewing reports with prior-election columns for 2001 and 2006;
the [year receipt](provenance/2011_report_year.json) preserves the evidence.
Both winner-report versions are retained without assuming that one supersedes
the other. The district folders do not establish statewide completeness.
The [Gaya Mukhiya pilot](2011/gaya_mukhiya/README.md) now provides 331 explicitly dated workbook winner records and separate tables for 338 PDF winners and 338 runner names. Both are assigned to 2011; extracted name differences require review against the originals. The pilot includes source/page/row references, discrepancy receipts and a field dictionary. The [district Mukhiya reports](2011/mukhiya_reports/README.md) now contain 4,320 winner records across 23 districts and 4,318 reservation labels, including the same 338 primary Gaya PDF records. Their election years are 2011, with the confirmation basis recorded in each row. A separate [judgment transcription](2011/khajuria_judgment/README.md) adds 11 candidates and votes for Khajuria in 2011 and corroborates one Bhojpur winner identity. Other offices and remaining earlier-year sources still need parsing.

## What Zenodo contains

[Zenodo record 22852474](https://doi.org/10.5281/zenodo.22852474), published on
22 September 2026 under CC0, contains 60 files totaling 2,787,457,212 bytes:

- 48 `rp.??` chunks forming the 2016 result-page archive (2,705 ledgers).
- A frame-page archive (228 ledgers) and reservation-roster archive (192 files).
- The three 2016 tables: seats, candidates and winners.
- The schema, dictionary, manifest, audit, checksums and deposit README.

Every file's size and MD5 in the public record matches the corresponding local
export file. The chunks concatenate to the SHA-256 of the local result archive.
The three tables, schema, dictionary, manifest and audit are byte-identical to
the repository versions checked during this pass. We checked the public metadata
against local bytes and downloaded the remote manifest to confirm its contents;
we did not re-download all 2.79 GB of payloads.

The public API response, per-file comparison and verification result are saved
in `provenance/zenodo_2016_record.json`, `provenance/zenodo_2016_files.csv` and
`provenance/zenodo_2016_verification.json`. Only small publication metadata and
the historical upload log remain under
`2016/interim/zenodo_export/`. Local export payloads were removed after comparing
them with the retained source files and published tables. The public deposit is
unchanged. Historical verification files describe the export before pruning;
consult `PRUNING.csv.gz` for its current local disposition.

The deposit does **not** contain 2021 sources, older-election sources, affidavits,
the independent legacy CSV collection, the generated `frame.parquet`, or this
repository's executable pipeline. The frame is reproducible from the deposited
frame pages using the offline command below. The independent audit's legacy-CSV
comparison therefore needs a separately available input.

## Restore and rebuild 2016 from Zenodo

Download the deposit's files into a temporary folder, such as
`/tmp/bihar-2016-download`, and verify the supplied checksums. From the repository
root, after downloading:

```sh
(cd /tmp/bihar-2016-download && cat rp.?? > bihar_2016_result_pages.tar && shasum -a 256 -c SHA256SUMS)
mkdir -p data/2016/raw/statewide
tar -xf /tmp/bihar-2016-download/bihar_2016_result_pages.tar -C data/2016/raw/statewide
tar -xf /tmp/bihar-2016-download/bihar_2016_frame_pages.tar -C data/2016/raw/statewide
tar -xf /tmp/bihar-2016-download/bihar_2016_reservation_rosters.tar -C data/2016/raw/statewide
uv run python scripts/sec_2016.py frame-offline --raw data/2016/raw/statewide
```

Keep the extracted source files as the working collection. After successful
checksum verification and extraction, the temporary chunks and tar files can
be deleted. They are transport packaging, not an additional source to retain.
The supplied tables are already in this repository; regenerating them is
optional. `make build-2016` reads the saved sources if regeneration is needed.
The full local inventory includes additional sources outside the Zenodo deposit,
so a Zenodo-only restore is checked using the deposit's own checksums.

## Other pipelines and deferred work

For 2021, `raw/statewide/` contains the acquisition checkpoints for all offices,
by-elections and current-term feeds. `raw/mukhiya_archive/` retains historical
archive and request receipts only. `raw/portal_snapshot_2026/` supplies the earlier
mukhiya current-feed snapshot. `raw/report/` and `raw/reservation_check/` hold
comparison sources. Distribution of sources beyond the existing Zenodo deposit
remains undecided.

An authenticated Harvard Dataverse check covered all 83 datasets accessible to
`@soodoku`, including drafts, plus public Bihar dataset and project-filename
searches. No Bihar local-election deposit was found. The related-looking
[PRI Seat Reservation Data](https://doi.org/10.7910/DVN/PQZVCO) record contains one
file, `haryana_mau_1995_2021.gz`. This describes the visible account and search
results, not deleted uploads or other accounts. Evidence is recorded in
`provenance/dataverse_check.json`. No remote data was changed.

Already-collected affidavit PDFs and request receipts are in
`2021/raw/affidavits/`; OCR text, page images and page-location caches are in
`2021/interim/affidavits/`. The checked-in review CSV remains an explicit manual
input to the published 64-winner transcription. It cannot be regenerated by OCR.
The general 2021 crawl stops after election tables and validation. Further
affidavit downloads, OCR and transcription are a distinct, deferred step.

SEC reconnaissance found a [2016 archive](https://sec.bihar.gov.in/archive),
[2021 election report](https://sec.bihar.gov.in/PanchayatRpt/ch1.aspx), and
[2026 Form 1 page](https://sec.bihar.gov.in/Prapatra1_ClaimObjection2026/).
The archive links separate 2016 contestant, winner, reservation and vote forms.
A five-request probe of the [winner form](https://sec.bihar.gov.in/old-sec/wcl.aspx)
returned 12 Mukhiya winners in Arwal block, Arwal district. Their candidate-name
set exactly matches the 12 published winners for that block. This is a bounded
independent comparison, not a statewide completeness check or a seat-key match.
Saved HTML and the comparison are in `provenance/sec_probe.json` and its linked
receipt. No affidavit links were followed. The other pages remain discovery
leads; no older-year download was established by this probe. No new data is
published remotely by this pass.

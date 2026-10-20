# Bihar election data

Use the Parquet files listed in the [repository README](../README.md). These are
parsed election records. [PROVENANCE.json](PROVENANCE.json) defines source origins,
collection dates, required inputs and the ordered script chains. Each dataset's
`MANIFEST.json` defines columns, missing values and source/output checksums.

Run `make data-summary` to regenerate the table from that specification. Raw files
and an external drive are not needed to update the guide.

<!-- data-summary:start -->

| Collection | Required originals | Processing chain | Published outputs | Archive |
| --- | --- | --- | --- | --- |
| 2011 | 23 district winner PDFs, Gaya winner workbook and runner-up PDF. Originals retain all pages and rows. | `local_elections_bihar.year2011.parse_reports` → `local_elections_bihar.year2011.parse_gaya` | `2011/mukhiya_reports/winner_records.parquet`<br>`2011/gaya_mukhiya/spreadsheet_winner_records.parquet`<br>`2011/gaya_mukhiya/runner_up_records.parquet` | 25 originals; 3.58 MB; [bihar_2011_sources.zip](https://zenodo.org/records/23092132/files/bihar_2011_sources.zip?download=1) |
| 2016 | Geography form responses and election results; request metadata and original response bodies travel together. | `local_elections_bihar.sources` → `local_elections_bihar.year2016.parse` | `2016/seats.parquet`<br>`2016/candidates.parquet`<br>`2016/winners.parquet` | 2,933 originals; 2.66 GB; [bihar_2016_sources_d01_d08.zip](https://zenodo.org/records/23092132/files/bihar_2016_sources_d01_d08.zip?download=1)<br>[bihar_2016_sources_d09_d16.zip](https://zenodo.org/records/23092132/files/bihar_2016_sources_d09_d16.zip?download=1)<br>[bihar_2016_sources_d17_d24.zip](https://zenodo.org/records/23092132/files/bihar_2016_sources_d17_d24.zip?download=1)<br>[bihar_2016_sources_d25_d32.zip](https://zenodo.org/records/23092132/files/bihar_2016_sources_d25_d32.zip?download=1)<br>[bihar_2016_sources_d33_d38.zip](https://zenodo.org/records/23092132/files/bihar_2016_sources_d33_d38.zip?download=1) |
| 2021 | General and by-election geography, candidates, results, phases and current-term feeds.<br>District/block names and current-term Mukhiya winners and reservations. | `local_elections_bihar.sources` → `local_elections_bihar.year2021.parse` | `2021/seats.parquet`<br>`2021/candidates.parquet`<br>`2021/result_rows.parquet`<br>`2021/winners.parquet`<br>`2021/byelection_seats.parquet`<br>`2021/byelection_candidates.parquet`<br>`2021/byelection_result_rows.parquet`<br>`2021/byelection_winners.parquet`<br>`2021/current_winners.parquet`<br>`2021/current_reservations.parquet` | 630,549 originals; 798.91 MB; [bihar_2021_sources.zip](https://zenodo.org/records/23092132/files/bihar_2021_sources.zip?download=1) |

Run `make parse YEAR=<year>` for the complete ordered chain. Intermediate geography tables are disposable `.cache/` files.

- District winner table contains all 338 Gaya primary PDF winners. Gaya workbook and runner-up lists remain separate source claims. Name differences have not been established as conflicts. Court transcription overlaps one district winner; counts are not additive.
- GP inferred from complete serial, block and exact reservation alignment of companion reports, corroborated by 25 block-first GP headings. Row-level linkage evidence is in runner_up_records.parquet.
- 2021 election, 2023/2025 by-elections and undated current-term feeds stay separate. Current reservations and occupants are not assigned retrospectively. Election-specific reservation linkage is incomplete.
- Matching codes or labels do not establish stable seat boundaries across general elections.

<!-- data-summary:end -->

## Reproduce a dataset

From the repository root:

```sh
uv sync --frozen
make fetch-sources YEAR=2011
make parse YEAR=2011
make verify YEAR=2011
```

Use `YEAR=2016`, `YEAR=2021` or `YEAR=all` for other pipelines. Fetching uses
the pinned Zenodo URLs and checksums in `PROVENANCE.json`. It verifies each
archive before extraction, preserves byte-identical existing sources and refuses
to overwrite differing files. If a download fails, rerun the command; already
restored files are checked again. If you already have the originals in the
listed layout, skip fetching. Parsing reads saved files and never collects live
pages. Missing election responses stay missing in 2021 status fields; parsing an
incomplete 2016 results capture requires the parser’s explicit `--partial` option.
Missing geography can stop frame reconstruction. No automatic recollection or
invented values fill those gaps.

The script chain may have several stages. For 2016 and 2021, saved geographic
responses first become `.cache/` seat frames; parsers combine those frames with
saved election responses to produce the Parquets. Intermediate frames can be
deleted and regenerated. They are not original data and do not belong in source
archives. The JSON lists each step's module, arguments and outputs.

```text
data/
  PROVENANCE.json          source origins, archive checksums and processing chains
  <year>/raw/             required original documents and responses
  <year>/*.parquet        published election datasets
  <dataset>/MANIFEST.json columns, interpretation, source/output checksums
.cache/                  disposable generated geography and transport packaging
```

Keep complete PDFs and workbooks, even when some rows do not enter an output.
Their page and row references allow checking the extraction against the original.
Saved web-response files also retain request parameters, URLs and collection dates.
Unused unique originals belong in one `unprocessed/<year>/` collection, separate
from reproduction inputs. Existing affidavit material is unchanged and excluded.
The reviewed Khajuria court transcription is a separate manual input, not a
script-generated dataset.

## Public source availability

[Zenodo 23092132](https://doi.org/10.5281/zenodo.23092132) contains seven source
ZIPs, sixteen Parquets and `bihar_code.zip` with source code, the lockfile,
documentation and manifests. Download the Parquets to use the data. To reproduce
a year, extract `bihar_code.zip` into an empty directory, then run the reproduction
commands above from that directory. `make fetch-sources` restores the originals
to `data/<year>/raw` automatically.

The 2016 sources are grouped by SEC district code: 01–08, 09–16, 17–24, 25–32
and 33–38. Each ZIP is independently extractable; no concatenation is needed.
Together they contain every required 2016 original exactly once. The fetch
command handles all five. The 2011 and 2021 collections each use one ZIP.
Zenodo Parquet filenames replace `/` in repository paths with `__`; the original
paths are listed in the provenance JSON.

[Zenodo 22852474](https://doi.org/10.5281/zenodo.22852474) remains the historical 2016
deposit. Its extra reservation PDFs and older packaging are not needed for the
current pipeline. Verification details and the scope of the Dataverse search
are in the provenance JSON.

To restore the historical 2016 deposit, download its files into a temporary
directory and follow its `README_DATA.md` and checksums. Concatenate `rp.??` into
the results tar, then extract the results and frame-page archives under
`data/2016/raw/statewide`. Reservation PDFs are not required for the three published
tables. Run `make parse YEAR=2016`; this reconstructs the geography offline.
Transport chunks and tar files can be removed after verified extraction.

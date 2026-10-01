# Bihar election data

Use the year folders for published seats, reservation labels, candidates and
winners. These tables are derived from original sources and are the usable data
products. Sources and their limitations are described in [PROVENANCE.md](PROVENANCE.md).
Further affidavit work, turnout and indirect leadership remain outside the current scope.

## Data summary

Run `make data-summary` to update the single table below. The script reads the
published datasets and measures the source directories; it does not download,
parse originals or create another inventory file. Regeneration requires the full
source collection to be mounted. Reading the table and using the published
datasets do not require that drive. Do not edit the generated section by hand.

<!-- data-summary:start -->

| Kind | Collection / office | Seats | Reservation labels | Candidates | Winners / runners | Files | Stored size | Location / availability |
| --- | --- | ---: | --- | ---: | --- | ---: | ---: | --- |
| Source collection | 2006 / central_handoff; .xls | — | — | — | — | 32 | 21.51 MB | `2006/raw/central_handoff`; external storage; distribution pending |
| Source collection | 2011 / central_handoff; .pdf, .xls | — | — | — | — | 291 | 56.37 MB | `2011/raw/central_handoff`; external storage; distribution pending |
| Working files / receipts | 2016 / zenodo_export; .log, .md, .py, no extension | — | — | — | — | 4 | 11.95 KB | `2016/interim/zenodo_export`; external storage; publication receipts only |
| Source collection | 2016 / legacy; .csv | — | — | — | — | 6 | 187.71 MB | `2016/raw/legacy`; external storage; distribution pending |
| Source collection | 2016 / statewide; .json, .jsonl.gz, .log, .parquet, .pdf | — | — | — | — | 3,127 | 2.75 GB | `2016/raw/statewide`; external storage; [Zenodo restore](#source-availability) |
| Working files / receipts (deferred) | 2021 / affidavits; .json, .png, .txt | — | — | — | — | 1,236 | 165.73 MB | `2021/interim/affidavits`; external storage; distribution pending |
| Working files / receipts | 2021 / archive; no extension | — | — | — | — | 1 | 866 B | `2021/interim/archive`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / check.log; .log | — | — | — | — | 1 | 1.63 KB | `2021/interim/check.log`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / download.log; .log | — | — | — | — | 1 | 11.97 KB | `2021/interim/download.log`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / download_status.json; .json | — | — | — | — | 1 | 222 B | `2021/interim/download_status.json`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / download_status.parquet; .parquet | — | — | — | — | 1 | 214.14 KB | `2021/interim/download_status.parquet`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / parsed; .json, .parquet | — | — | — | — | 3 | 9.22 MB | `2021/interim/parsed`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / pipeline_status.json; .json | — | — | — | — | 1 | 1.88 KB | `2021/interim/pipeline_status.json`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / release.log; .log | — | — | — | — | 1 | 1.16 KB | `2021/interim/release.log`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / structured_source_search.json; .json | — | — | — | — | 1 | 2.43 KB | `2021/interim/structured_source_search.json`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / throughput.json; .json | — | — | — | — | 1 | 368 B | `2021/interim/throughput.json`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / throughput.log; .log | — | — | — | — | 1 | 304 B | `2021/interim/throughput.log`; external storage; distribution pending |
| Working files / receipts (deferred) | 2021 / vision_validation; .json, .log | — | — | — | — | 3 | 60.41 KB | `2021/interim/vision_validation`; external storage; distribution pending |
| Source collection (deferred) | 2021 / affidavits; .json, .jsonl, .jsonl.gz, .pdf | — | — | — | — | 2,721 | 3.25 GB | `2021/raw/affidavits`; external storage; distribution pending |
| Source collection | 2021 / mukhiya_archive; .json, no extension | — | — | — | — | 3 | 9.74 MB | `2021/raw/mukhiya_archive`; external storage; distribution pending |
| Source collection | 2021 / portal_snapshot_2026; .jsonl.gz, .parquet | — | — | — | — | 1,304 | 3.23 MB | `2021/raw/portal_snapshot_2026`; external storage; distribution pending |
| Source collection | 2021 / report; .html.gz | — | — | — | — | 2 | 64.59 KB | `2021/raw/report`; external storage; distribution pending |
| Source collection | 2021 / reservation_check; .jsonl.gz | — | — | — | — | 5 | 103.61 KB | `2021/raw/reservation_check`; external storage; distribution pending |
| Source collection (deferred) | 2021 / source_search; .html, .js, .pdf, .png | — | — | — | — | 7 | 11.40 MB | `2021/raw/source_search`; external storage; distribution pending |
| Source collection | 2021 / statewide; .gz, .jsonl.gz, .parquet | — | — | — | — | 629,456 | 797.09 MB | `2021/raw/statewide`; external storage; distribution pending |
| Source collection | undated / central_handoff; .xls | — | — | — | — | 72 | 40.36 MB | `undated/raw/central_handoff`; external storage; distribution pending |
| Published records | 2016 general / ward member | 114,583 | 103,469 | 277,148 | 97,515 | — | — | [Dataset](2016/) |
| Published records | 2016 general / panch | 114,583 | 95,465 | 136,021 | 85,692 | — | — | [Dataset](2016/) |
| Published records | 2016 general / mukhiya | 8,402 | 8,133 | 96,257 | 7,942 | — | — | [Dataset](2016/) |
| Published records | 2016 general / sarpanch | 8,402 | 8,139 | 45,054 | 7,881 | — | — | [Dataset](2016/) |
| Published records | 2016 general / panchayat samiti member | 11,142 | 11,142 | 80,259 | 10,793 | — | — | [Dataset](2016/) |
| Published records | 2016 general / zila parishad member | 983 | 983 | 10,126 | 894 | — | — | [Dataset](2016/) |
| Published records | 2021 general / ward member | 109,641 | Unknown | 505,438 | 109,510 | — | — | [Dataset](2021/) |
| Published records | 2021 general / panch | 109,641 | Unknown | 216,429 | 106,656 | — | — | [Dataset](2021/) |
| Published records | 2021 general / mukhiya | 8,067 | Unknown | 66,430 | 8,050 | — | — | [Dataset](2021/) |
| Published records | 2021 general / sarpanch | 8,067 | Unknown | 49,698 | 8,044 | — | — | [Dataset](2021/) |
| Published records | 2021 general / panchayat samiti member | 11,095 | Unknown | 73,778 | 11,065 | — | — | [Dataset](2021/) |
| Published records | 2021 general / zila parishad member | 1,160 | Unknown | 12,935 | 1,150 | — | — | [Dataset](2021/) |
| Published records | 2023 1 byelection / ward member | 533 | Unknown | 1,092 | 533 | — | — | [Dataset](2021/) |
| Published records | 2023 1 byelection / panch | 2,002 | Unknown | 2,158 | 2,002 | — | — | [Dataset](2021/) |
| Published records | 2023 1 byelection / mukhiya | 48 | Unknown | 273 | 48 | — | — | [Dataset](2021/) |
| Published records | 2023 1 byelection / sarpanch | 54 | Unknown | 275 | 54 | — | — | [Dataset](2021/) |
| Published records | 2023 1 byelection / panchayat samiti member | 44 | Unknown | 180 | 44 | — | — | [Dataset](2021/) |
| Published records | 2023 1 byelection / zila parishad member | 7 | Unknown | 66 | 7 | — | — | [Dataset](2021/) |
| Published records | 2023 2 byelection / ward member | 321 | Unknown | 530 | 321 | — | — | [Dataset](2021/) |
| Published records | 2023 2 byelection / panch | 788 | Unknown | 825 | 788 | — | — | [Dataset](2021/) |
| Published records | 2023 2 byelection / mukhiya | 20 | Unknown | 112 | 20 | — | — | [Dataset](2021/) |
| Published records | 2023 2 byelection / sarpanch | 34 | Unknown | 126 | 34 | — | — | [Dataset](2021/) |
| Published records | 2023 2 byelection / panchayat samiti member | 20 | Unknown | 61 | 20 | — | — | [Dataset](2021/) |
| Published records | 2023 2 byelection / zila parishad member | 4 | Unknown | 27 | 4 | — | — | [Dataset](2021/) |
| Published records | 2025 1 byelection / ward member | 733 | Unknown | 959 | 733 | — | — | [Dataset](2021/) |
| Published records | 2025 1 byelection / panch | 915 | Unknown | 955 | 915 | — | — | [Dataset](2021/) |
| Published records | 2025 1 byelection / mukhiya | 63 | Unknown | 290 | 63 | — | — | [Dataset](2021/) |
| Published records | 2025 1 byelection / sarpanch | 83 | Unknown | 282 | 83 | — | — | [Dataset](2021/) |
| Published records | 2025 1 byelection / panchayat samiti member | 72 | Unknown | 204 | 72 | — | — | [Dataset](2021/) |
| Published records | 2025 1 byelection / zila parishad member | 8 | Unknown | 34 | 8 | — | — | [Dataset](2021/) |
| Parsed source list | 2011 / gaya mukhiya spreadsheet winner records / mukhiya | Unknown | Unknown | Unknown | 330 | — | — | [Dataset](2011/gaya_mukhiya/) |
| Parsed source list | 2011 / mukhiya reports winner records / mukhiya | Unknown | 3,971 | Unknown | 3,973 | — | — | [Dataset](2011/mukhiya_reports/) |
| Parsed source list | 2011 / gaya mukhiya runner up records / mukhiya | Unknown | 337 | Unknown | 337 runners | — | — | [Dataset](2011/gaya_mukhiya/) |
| Manual transcription | 2011 / khajuria judgment / mukhiya | Unknown | Unknown | 11 | 1 | — | — | [Dataset](2011/khajuria_judgment/) |
| Published snapshot | Undated 2021-term feed / ward member | Unknown | 109,641 | Unknown | 109,641 | — | — | [Dataset](2021/) |
| Published snapshot | Undated 2021-term feed / panch | Unknown | 109,641 | Unknown | 109,641 | — | — | [Dataset](2021/) |
| Published snapshot | Undated 2021-term feed / mukhiya | Unknown | 8,067 | Unknown | 8,067 | — | — | [Dataset](2021/) |
| Published snapshot | Undated 2021-term feed / sarpanch | Unknown | 8,067 | Unknown | 8,067 | — | — | [Dataset](2021/) |
| Published snapshot | Undated 2021-term feed / panchayat samiti member | Unknown | 11,095 | Unknown | 11,095 | — | — | [Dataset](2021/) |
| Published snapshot | Undated 2021-term feed / zila parishad member | Unknown | 1,160 | Unknown | 1,160 | — | — | [Dataset](2021/) |

Stored source/working collection: **7.31 GB (7,307,234,801 bytes; 638,282 files)**, measured from file sizes on 2026-10-01 (UTC). Filesystem metadata files are excluded. Published datasets and repository documentation are excluded from this storage total.

Source collections contain original documents/responses and their acquisition metadata. Working files include caches, generated intermediates and receipts. Published records are derived, usable election data; manual transcriptions are reviewed inputs that cannot be regenerated by code alone.

**Reading the counts:** Seats means source frame rows, including ambiguous seat codes. Reservation labels means nonblank labels, not only reserved seats. For source lists it counts labeled records, not unique seats. Candidates and winners count records, not necessarily unique people. Unknown means the source does not establish the count; 0 is an observed zero. A dash means the column does not apply to that row. File counts and sizes belong to storage bundles and are not allocated again to offices or election rounds.

- District Mukhiya reports include the 338 Gaya pilot PDF records, counted once here. The Khajuria judgment winner overlaps one district-report record; source totals are not additive.
- A reported reservation label is not independent confirmation of its correctness.
- Current-term reservations are not assigned to general or by-elections retrospectively.
- Seat coverage is conditional on the collected frame, not proof of statewide completeness.
- 2011 winner/runner records do not establish a unique-seat frame or all-candidate coverage.
- Cross-general-election links have not been established; within-term by-election membership already exists separately.

The 2006 and undated source collections remain unparsed; 2011 is partially parsed. Snapshot labels and current winners are displayed separately from election-specific records. Source-list winners remain provisional until reconciled. Winner determination is documented in each dataset.

<details>
<summary>Inputs used to generate this table (SHA-256)</summary>

- `2011/gaya_mukhiya/runner_up_records.parquet`: `1fc230fd05afb6120ff2dee6cdab3d8fe2ebb1a21461fbe76946e0140ff4fa8b`
- `2011/gaya_mukhiya/spreadsheet_winner_records.parquet`: `de346806cf37a480c6efd9942949fab59e17e9b9e9d2f44afe399f587c54a15f`
- `2011/khajuria_judgment/candidates.csv`: `ce065e676ceb9056da2121dd8d254fbb210785d572cc79608e4c9ef5b2c9fc63`
- `2011/mukhiya_reports/winner_records.parquet`: `3cdb740e116412a27d059df0b42c0dd05523069de636683f7c0d997a73437c56`
- `2016/candidates.parquet`: `0b73373fce5b29292c61399b3308d44b95f850f17127f5c2e6bfef3e162f65ca`
- `2016/seats.parquet`: `5f234dad9afc7603e37aa34401ff4210fee31e6448cb8f94d79737a667d1761c`
- `2016/winners.parquet`: `1f1712f0a91370cb3db6a4b891d419a60cd81a4a7dbc00c57ea04e4fc14aeb13`
- `2021/byelection_candidates.parquet`: `c2686d60f0678ca3dbb8e79e1127d78bc9aa19f03570084ce6ae2c20aa99f4f8`
- `2021/byelection_seats.parquet`: `a6bf0939e4e50c79161efb0d03b6425a7499b792a676d4f6db77049f817b6aef`
- `2021/byelection_winners.parquet`: `c6445333c4109b108bb36681e530bce0de9f31e343d9e7636ca9bb258cf0153b`
- `2021/candidates.parquet`: `8e6fda01045edf245cc0c7d46665f3496c5e41323775a3900300a9ae0b9537be`
- `2021/current_reservations.parquet`: `a432377012f1d55f5862f44fe3f9f8a4b391b1b215fc44c5d5d626f96dc71073`
- `2021/current_winners.parquet`: `55d47177250629cd87f35413645feb613a682bba3308898894b6204732c35cd4`
- `2021/seats.parquet`: `690f4e18e5e73558bb578f539b1c957c09dd17469b49726f69961c636b3d1fab`
- `2021/winners.parquet`: `32c40abc700179c19c8ff0c36ce860c34640e22a3be534f51fb77f78031b3c10`
- `scripts/reporting/summary.py`: `d52ea32cdb6f077b5ae221bc5813b4d0e1f84569e47a1f356ed822eb4f943ebc`
- `scripts/reporting/storage.py`: `75526e88a2ecd5b7958a6d34813c2485939a917d4048db5730e453952513be2f`

</details>

<!-- data-summary:end -->

## Files and locations

```text
data/
  README.md                 generated summary and usage instructions
  PROVENANCE.md              source origins, dates, checks and limitations
  <year>/
    raw/                    original source collection and acquisition metadata
    *.parquet               published datasets
    MANIFEST.json           dataset source/output references and hashes
```

Manual transcriptions and review inputs are retained with the relevant dataset.
They cannot be recreated by rerunning extraction code. Disposable caches belong
in ignored `.cache/` or a temporary directory; there is no required `interim/`
layer. Existing deferred affidavit tools still use their historical working
locations, which are included in the size summary and left untouched.

On the maintainer's machine, source directories live under
`/Volumes/Staging/local_elections_bihar/<year>/raw`. Ignored links at
`data/<year>/raw` point there. Other users can put restored sources directly at
`data/<year>/raw`, or link that path to their own storage. Parsers accept explicit
input paths; the external drive's name is not a requirement.

Published datasets can be used without raw sources. `make verify` checks the
2016 and 2021 published datasets. Parsing originals is a separate, explicit task.
Dataset manifests record source hashes and extraction details; they are not a
history of filesystem moves or deletions.

## Source availability

The 2016 SEC source deposit is [Zenodo 22852474](https://doi.org/10.5281/zenodo.22852474).
It contains 48 chunks of result-page archives, frame pages, reservation rosters,
the three published tables and documentation. The verification scope and limits
are recorded in [PROVENANCE.md](PROVENANCE.md). Temporary download chunks and
archives are transport packaging; retain the extracted sources after verification.

There is no established public download for the complete older-year handoff or
2021 raw collection. The Harvard Dataverse account/search check found no Bihar
local-election deposit within its stated scope. Do not treat local paths as
available downloads. Sources for 2006 and unresolved years remain unparsed;
2011 is partially parsed. Refer to the 2011 dataset notes before combining sources.

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
uv run python -m scripts.year2016.collect frame-offline --raw data/2016/raw/statewide
```

Keep the extracted source files as the working collection. After successful
checksum verification and extraction, the temporary chunks and tar files can
be deleted. They are transport packaging, not an additional source to retain.
The supplied tables are already in this repository; regenerating them is
optional. `make build-2016` reads the saved sources if regeneration is needed.
The full local inventory includes additional sources outside the Zenodo deposit,
so a Zenodo-only restore is checked using the deposit's own checksums.

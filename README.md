# Bihar local-election data

Seat reservations, candidates and winners for Bihar's rural local governments.
The published data cover the 2016 and 2021 general elections for all six panchayat
offices, subsequent by-elections, and a partial 2011 Mukhiya collection.

## Published datasets

Use these Parquet files directly; no raw-data drive or parsing step is needed.
The list is generated from the published files by `make data-summary`.

<!-- datasets:start -->

| File | Rows | Each row represents |
| --- | ---: | --- |
| [2011/gaya_mukhiya/runner_up_records.parquet](data/2011/gaya_mukhiya/runner_up_records.parquet) | 337 | Gaya Mukhiya runner-up with GP linked from the companion winner PDF |
| [2011/gaya_mukhiya/spreadsheet_winner_records.parquet](data/2011/gaya_mukhiya/spreadsheet_winner_records.parquet) | 330 | Gaya Mukhiya winner with GP and block (Excel) |
| [2011/mukhiya_reports/winner_records.parquet](data/2011/mukhiya_reports/winner_records.parquet) | 3,973 | Mukhiya winner reported in a 2011 district PDF (23 districts, including Gaya) |
| [2016/candidates.parquet](data/2016/candidates.parquet) | 644,865 | Candidate record |
| [2016/seats.parquet](data/2016/seats.parquet) | 258,095 | Seat in the election frame |
| [2016/winners.parquet](data/2016/winners.parquet) | 210,717 | Winner record, with determination basis |
| [2021/byelection_candidates.parquet](data/2021/byelection_candidates.parquet) | 8,449 | Candidate in a by-election round |
| [2021/byelection_result_rows.parquet](data/2021/byelection_result_rows.parquet) | 4,643 | Source result record in a by-election round |
| [2021/byelection_seats.parquet](data/2021/byelection_seats.parquet) | 5,749 | Seat in a by-election round |
| [2021/byelection_winners.parquet](data/2021/byelection_winners.parquet) | 5,749 | Winner in a by-election round |
| [2021/candidates.parquet](data/2021/candidates.parquet) | 924,708 | Candidate record |
| [2021/current_reservations.parquet](data/2021/current_reservations.parquet) | 247,671 | Undated current-term seat-reservation record |
| [2021/current_winners.parquet](data/2021/current_winners.parquet) | 247,671 | Undated current-term winner-feed record |
| [2021/result_rows.parquet](data/2021/result_rows.parquet) | 968,562 | Source result record; see dataset grain |
| [2021/seats.parquet](data/2021/seats.parquet) | 247,671 | Seat in the election frame |
| [2021/winners.parquet](data/2021/winners.parquet) | 244,475 | Winner record, with determination basis |

<!-- datasets:end -->

The [Khajuria judgment transcription](data/2011/khajuria_judgment/) supplies eleven
candidates and their votes for one 2011 contest. Its CSV is the manually reviewed
input, with source references in its manifest.

For **2011**, start with `2011/mukhiya_reports/winner_records.parquet`: winner
names and seat-reservation labels transcribed from district PDFs, including Gaya.
Every published row has district, block, GP and winner name. Exact content
repeats and records with unresolved locations are excluded; other repeated seat
labels remain flagged.

The [Gaya files](data/2011/gaya_mukhiya/) add workbook winners with GP labels and
runner-up records whose GP labels are **inferred from the companion winner PDF**.
The runner links require matching serials, blocks and exact reservation text
throughout both reports, with corroborating GP headings. Each row records the
link basis and its sources. Workbook and PDF winner claims remain separate.

The [2021 reservation comparison](data/2021/reservation_check/) retains supporting
records and unresolved differences. Existing [affidavit work](data/2021/affidavits/README.md)
is separate; further collection and extraction are deferred.

## Columns and limitations

Each dataset's `MANIFEST.json` contains its column definitions, missing-value
conventions, source references, file hashes and validation findings. Original
values remain beside parsed or normalized values where applicable. Missing is
not zero, male, unreserved or an inferred winner.

- **2011:** Mukhiya winner lists from 23 districts, not statewide candidate
  coverage. The district collection already includes Gaya's PDF records. The
  workbook winners remain separate pending review of extracted-name differences.
  Runner GP links are inferred and explicitly labeled. Records with unresolved
  locations or missing names are excluded, as are exact content repeats. Other
  repeated seat labels remain flagged; counts are not verified unique seats.
- **2016:** Election-specific reservation labels are available. Some source
  geography codes identify multiple seats; ambiguity is retained in the tables.
- **2021:** Election results and undated current-term feeds are distinct.
  Snapshot reservation labels are not verified assignments for the 2021 election
  or its by-elections. `result_rows` retains the source result grain; it is not
  an additional candidate roster.
- **Winners:** `winner_basis` distinguishes source flags from derivations such
  as uncontested or sole-candidate outcomes. A current occupant does not replace
  the recorded election winner.
- **Across years:** No validated cross-election seat panel is published.
  Matching names or codes alone does not establish geographic continuity.

See the [generated data summary](data/README.md#data-summary) for record counts,
source inputs and processing chains, and [source provenance](data/PROVENANCE.json)
for acquisition, dating evidence and unresolved issues.

## Use

```python
import polars as pl

seats = pl.read_parquet("data/2016/seats.parquet").filter(pl.col("office") == "mukhiya")
winners = pl.read_parquet("data/2016/winners.parquet").filter(
    pl.col("office") == "mukhiya"
)
```

`make verify` checks the published datasets for all three years locally. Parsing or
collecting sources is optional and explicit; the [scripts guide](scripts/README.md)
lists the commands. `make check` runs local code checks and tests.

## Sources and reproduction

Original SEC responses, PDFs and workbooks are kept separately from published
tables under `data/<year>/raw`. The [data guide](data/README.md) lists the
required originals, public availability and ordered processing commands.
`make parse YEAR=2011` runs the 2011 pipeline; substitute 2016 or 2021 as needed.
Published tables can be used without downloading originals.

The three required-source archives are prepared; their sizes and checksums are in
[data/PROVENANCE.json](data/PROVENANCE.json). The new project-wide Zenodo deposit is
still a draft because large uploads timed out. These archives are not yet public
downloads. The earlier [2016 deposit](https://doi.org/10.5281/zenodo.22852474)
remains available, with restoration instructions in the data guide.

## Scope and collection priorities

Recover seat reservations, contestants and election outcomes for the six directly
elected panchayat offices, across general elections and by-elections. Municipalities,
indirect leadership, turnout, polling logistics and further affidavit work are
outside the current task. Retain partial sources with explicit limits.

## Citation and license

Cite the files and repository commit used. For the historical 2016 deposit, cite
[Zenodo 22852474](https://doi.org/10.5281/zenodo.22852474).
Code is [MIT licensed](LICENSE), including attribution for Ravi Taak's Kruti Dev
mapping. Election records were published by the Bihar State Election Commission;
no blanket data license is asserted for all collections.

## 🔗 Adjacent Repositories

- [in-rolls/local_elections_uttarakhand](https://github.com/in-rolls/local_elections_uttarakhand) — Data on Local Elections from Uttarakhand
- [in-rolls/local_elections_up](https://github.com/in-rolls/local_elections_up) — UP Local Election Data --- GP and ULB. Seat reservation, winner, and candidates for some elections
- [in-rolls/local_elections_kerala](https://github.com/in-rolls/local_elections_kerala) — Kerala Local Government Seat Reservation Data and Winner Attributes
- [in-rolls/local_elections_rajasthan](https://github.com/in-rolls/local_elections_rajasthan) — Rajasthan GP Election Reservation Status and Results for 2020--2022
- [in-rolls/electoral_rolls_bihar_2020](https://github.com/in-rolls/electoral_rolls_bihar_2020) — Bihar Electoral Rolls 2020

_Powered by [Adjacent](https://github.com/gojiplus/adjacent)_

<!-- adjacent:end -->

## Maintenance

This is a point-in-time data collection; see the [shared maintenance policy](https://github.com/soodoku/data-repos#maintenance-policy). Run the affected parser tests when code changes and the relevant data validators when inputs or outputs change. Full-data checks and publication are explicit operations. Routine edits do not require hosted CI, Docker, a Python-version matrix, Preen or pre-commit.

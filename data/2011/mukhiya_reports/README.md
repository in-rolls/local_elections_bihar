# District Mukhiya winner reports

[winner_records.parquet](winner_records.parquet) contains **4,320 winner records from 23 district reports, 311 pages**, including 4,318 nonblank reservation labels. These reports came from the historical 2011 handoff collection. Both `collection_year` and `election_year` are 2011. The maintainer identified the reports as 2011, noting that “पूर्व निर्वाचित” refers to prior service in 2001 and 2006. The [year receipt](../../provenance/2011_report_year.json) preserves that confirmation and its scope. These are source transcriptions, not a verified statewide seat roster.

The table includes the same 338 primary Gaya PDF records as the [Gaya pilot](../gaya_mukhiya/README.md); do not add those counts. The explicitly dated Gaya workbook has 331 winner records and remains separate pending review of extracted name differences. The [Khajuria judgment transcription](../khajuria_judgment/README.md) independently supports one reported winner's 2011 election, without dating the whole report or its reservation labels.

## Contents and limits

Each record preserves panchayat and block labels, winner and relative names, seat reservation, candidate category, gender, age and other printed attributes. Seat reservation and candidate category are separate columns. No votes or losing candidates occur in these winner reports. Record IDs identify source rows, not verified unique people or seats.

- [coverage.csv](coverage.csv): district counts and extraction gaps. Coverage varies sharply: Jamui has only 17 records. District presence does not imply complete district coverage.
- [reservation_labels.csv](reservation_labels.csv): every distinct raw label, its frequency and conservative recodes. 3,336 records have a mapped reservation category; 2,983 have explicit female/other reservation status. BC and EBC remain distinct as written. Bare abbreviations such as `अनु0` are ambiguous and remain unmapped. An unreserved category alone does not establish whether a seat was reserved for women.
- [issues.csv](issues.csv): five cells with unresolved glyph ordering are null, with source location and diagnostic text retained. Other invalid numeric fields also receive receipts. Empty source cells remain empty raw strings; null raw cells denote decoding failures.
- 46 records have no readable block label recovered from the heading, flagged by `missing_block`; headings are not carried forward. Madhubani page 12, for example, renders boxes in place of the block name. 841 records share a literal block/panchayat label with another record. They are retained and flagged, not collapsed into seats. Repeat-label flags are null when the required labels are missing. `duplicate_of_record_id` links a later row to its first occurrence when every decoded source cell and the block label match within the same PDF; rows with decoding failures are excluded from this check. This identifies 300 repeated records, including 151 in Saharsa, leaving 4,020 records after that filter. Filter to null duplicate references to remove these exact content repeats, but do not treat the remainder as verified unique seats.
- [dictionary.csv](dictionary.csv): columns, types and missing-value meanings. Ages outside 18–120 are null in the numeric column and preserved as printed in `age_raw`. Gender uses only explicit source labels, never names.

## Reproduce and check

Originals have one canonical home under `/Volumes/Staging/local_elections_bihar/2011/raw/central_handoff/`, exposed locally through `data/2011/raw/`. No duplicate PDFs or repaired intermediates are retained. With the original files mounted:

```sh
uv sync --frozen --group dev
uv run python scripts/parse_2011_reports.py
```

`make parse-2011` regenerates both the Gaya comparison and these district records. Parsing works offline. [MANIFEST.json](MANIFEST.json) fingerprints all 23 original PDFs and the parser/map inputs, declares the nullable schema and fingerprints the output files. CHECKSUMS verifies the final tables and receipts. Each row also contains the original file hash, one-based PDF page, printed serial and bounding box in PDF points.

The parser repairs embedded Hindi font maps in memory and reads table cells in drawing order; it does not use OCR. Committed glyph maps allow parsing without the proprietary reference font. To independently rederive the maps, the exact SHA-pinned Arial Unicode font is required:

```sh
uv run python scripts/map_fonts_2011.py \
  --font '/System/Library/Fonts/Supplemental/Arial Unicode.ttf' \
  --glob 'winners/*/*GPM.pdf' --out /tmp/font_map_2011.json
```

All source serials are checked for uninterrupted order within each PDF. Printed office headings are checked on every page. Sixteen additional records were visually checked against original Bhojpur and Begusarai pages; those field transcriptions are in `tests/fixtures/2011/district_visual_review.csv`, alongside the existing 32-record Gaya review. This limited sample is an extraction regression check, not a population error-rate estimate or independent verification of what the source reports.

Remaining work includes reviewing Gaya name differences, parsing the five other offices and remaining alternate/runner reports, and establishing seat identities from geographic evidence. None of those are silently inferred by this table.

# Sources and interpretation

This project collects Bihar panchayat seat reservations, candidates and winners.
Each dataset's `MANIFEST.json` records its columns, source references, checksums
and substantive validation results. Manual transcriptions are inputs, not
reproducible outputs of an OCR command.

## Earlier elections and the 2011 reports

The historical collection came from `data/bihar` in
[in-rolls/local_elections at fa4c4e79](https://github.com/in-rolls/local_elections/tree/fa4c4e79/data/bihar).
Original files are under `2006/raw/central_handoff`, `2011/raw/central_handoff`
and `undated/raw/central_handoff`. A public download for the full handoff has not
been established.

Thirty-two other-office workbooks have 2006 headings. Gaya's Mukhiya workbook
explicitly states 2011. The remaining 37 Mukhiya and 35 Sarpanch workbooks remain
undated; their folder names do not establish election years.

On October 1, 2026, the maintainer confirmed the PDF collection as **2011**:
“these are all for 2011. there is a 'purva nirvachit' for 2001/2006 so 2011”.
This covers primary and alternate winners and companion runner lists.
The reviewed examples were the primary and alternate Gaya reports and the
Bhojpur winner report. “पूर्व निर्वाचित” describes prior elected office in
2001/2006. This is collection identification, not a printed 2011 date checked
on every page; prior-election columns alone do not logically exclude every
later year.

The district extraction includes the Gaya pilot's 338 primary PDF records.
The Khajuria judgment corroborates one Bhojpur winner and supplies one contest's
candidate list. These sources overlap and their counts must not be added.
Gaya workbook/PDF extracted-name differences need review against originals;
they are not established source conflicts. Unrelated undated workbooks have
not been reclassified.

## 2016 sources and public deposit

The [SEC results form](https://sec.bihar.gov.in/old-sec/ovc.aspx) was collected
in September 2026. Saved form responses and reservation PDFs are under
`2016/raw/statewide`; the independently collected earlier CSV snapshot is under
`2016/raw/legacy`. Parsers read saved sources without contacting the SEC.

[Zenodo 22852474](https://doi.org/10.5281/zenodo.22852474) contains 60 files,
2,787,457,212 bytes: 48 result-archive chunks, frame-page and reservation-roster
archives, the three published tables and documentation. On October 1, 2026,
public API sizes and MD5 checksums matched the local export; the remote manifest
was downloaded and byte-matched. The other remote payloads were not downloaded
again. The concatenated result archive's SHA-256 is
`8f58b5883f58a7069be8c23702ff7f4d275b15eea2fa3fc21b0391525401c607`.

The deposit excludes the legacy CSV comparison, earlier-election sources, 2021
sources and affidavits. Local duplicate export payloads are not retained.
The deposited documentation describes its original version; local metadata has
since been consolidated. The election tables are unchanged by that consolidation.

## 2021-term sources

The [SEC portal](https://sec25.bihar.gov.in) was collected in September 2026.
Saved request/response ledgers under `2021/raw/statewide` supply candidate lists,
results, election rounds and current-term feeds. The earlier current-feed
snapshot is under `2021/raw/portal_snapshot_2026`.

The 2021 general election, 2023/2025 by-elections and undated current-term feeds
remain separate. Later reservations or seat occupants are not retrospectively
assigned to an earlier election. Election-specific reservation linkage remains
incomplete. Matching labels or codes across years does not establish unchanged
seat boundaries.

## Source searches and checks

On October 1, 2026, an authenticated Harvard Dataverse search covered all 83
datasets accessible to `@soodoku`, including drafts, and public Bihar/project
filename searches. No Bihar local-election deposit was found within that scope.
[PRI Seat Reservation Data](https://doi.org/10.7910/DVN/PQZVCO) contained
`haryana_mau_1995_2021.gz`. This cannot rule out deleted uploads, other accounts
or unrelated filenames.

The [SEC archive](https://sec.bihar.gov.in/archive) labels its older candidate,
vote and winner forms as 2016. A five-request check of its
[winner form](https://sec.bihar.gov.in/old-sec/wcl.aspx) returned 12 Mukhiya
winner names for Arwal block, Arwal district, matching the published name set.
This was not a seat-key comparison or a statewide completeness check.
No verified 2011 candidate-results endpoint was found in the inspected pages
and targeted searches; that is not proof that none exists.

Turnout, polling logistics, indirect leadership and further affidavit work are
deferred. Existing affidavit sources and manual review inputs are unchanged.
Search findings are retained here; full search dumps, probing responses and
routine execution logs are not maintained as project artifacts.

## Retention

Keep necessary original sources, reviewed manual inputs and published datasets.
Source/output hashes belong with their datasets. Duplicate packaging, disposable
caches and histories of file moves or deletions are not maintained artifacts.
There is no claimed full-drive integrity verification. The generated data-guide
table measures current storage separately from dataset validation.

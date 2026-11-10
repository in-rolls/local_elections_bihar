# Patna municipal election sources

This handoff contains all 75 official ward-councilor winner records for 2017 and 2022 and 1,008 TCPD candidate records for 2017. It excludes mayor and deputy-mayor offices. Sources were collected November 9, 2026 UTC. No effects are estimated.

| Source | Winners | Recorded women | Women-reserved wards | Education present |
|---|---:|---:|---:|---:|
| Official 2017 winner grid | 75 | 48 | 36 | 75 |
| Official 2022 phase-II winner API | 75 | 47 | 36 | 0 |

These are recorded values, not a certification that every source field is correct. Ward 26's 2017 winner is recorded as male in both the official grid and TCPD, although the signed reservation notification reserves the ward for women. The raw sex and derived indicator are preserved with `sex_reservation_conflict=true`; neither reservation nor the person's name is used to overwrite sex. The attempted affidavit request returned HTML, not an affidavit, and is retained with that failure noted. This record requires independent resolution before using it as a validated outcome.

## Sources and reconciliation

The official [2017 winner grid](https://sec.bihar.gov.in/old-sec/UWCL.aspx) was retrieved through its district/body selectors and all four pages. The [signed reservation notification](https://sec.bihar.gov.in/old-sec/Reservation/ULBReservation/Patna.pdf), physical pages 20–23, supplies the adopted 2017 treatment. A checked transcription retains PDF pages and row numbers. The winner grid incorrectly labels ward 32 as open and ward 35 as BC; the notification shows women-reserved general and open general, respectively. Both source values remain available in the output and conflict report. Starred annotations in the PDF may refer to older assignments, but their year is unresolved; they are not treated as 2012 reservations.

The official [2022 phase-II winner endpoint](http://sec2021.bihar.gov.in/SEC_NP_P2_01/Admin/WinningCandidatesPost_Wise.aspx) returns 75 Patna ward councilors through `GetWinningCandidtes`, using district 28, corporation 310 and office 3. The original form, controls JavaScript, JSON response and request parameters are retained. Its `age` is retrieval-year dependent and is **not age at the 2022 election**. Education is absent and remains null. Affidavit URLs are retained as links, not evidence that their documents were downloaded. The endpoint is labeled for the 2022 election; a full independent check of winner identities against the contemporaneous gazette has not been completed.

The API encodes wards 22A, 22B and 22C as 73, 74 and 75. Its retained controls JavaScript explicitly supplies these aliases. Raw IDs and normalized labels are both preserved. This is a within-source label interpretation, not proof of geographic continuity across elections.

The pinned TCPD/CASI ULB 1.1 file remains in `../local_elections/data/reference/tcpd/`; it is read in place, not copied. All 75 first-place candidates agree with the official 2017 winners on recorded sex and age. Two names differ only by doubled spaces. This agreement does not establish independent validation because TCPD may derive from the same official source. Its ward reservation field is blank; the signed notification supplies the joined reservation. Its reported May 21, 2017 polling date is preserved as reported, not adopted as a verified Patna election date. Original name, category, education, votes, position and raw record remain traceable.

## Implications for the urban analysis

After reconciling the notification, all 75 ward labels have the same reservation category in 2017 and 2022: 36 remain women-reserved and 39 remain nonquota. There are **zero observed quota-to-nonquota transitions** in this pair. It therefore adds no post-quota persistence comparison. The label-linked transition file explicitly marks geographic equivalence unverified. The two waves can support separate descriptive or repeated-reservation analyses after the relevant source and design checks; they are not automatically added to a causal pool.

The recorded women-winner counts in nonquota wards are 13/39 in 2017 and 11/39 in 2022. These are descriptive shares under the adopted reservation sources, not effects of prior reservation. The 2017 sex conflict lies in a reserved ward.

## Files and reproduction

Outputs are in `data/release/urban/patna/`:

- `winners.parquet`: 150 winner records, with source-specific fields and conflict flags.
- `candidates_2017.parquet`: 1,008 candidate records, joined to the signed reservation roster.
- `ward_transitions.parquet`: 75 ward-label comparisons, explicitly not a validated geographic crosswalk.
- `source_conflicts.json`, `profile.json`, `schema.json`, `checksums.sha256`: discrepancies, coverage, types and output hashes.

`data/raw/urban/patna/receipts.jsonl` records URLs, request parameters, retrieval times, content types, byte counts and SHA-256 hashes. `transcription_receipt.json` pins both the manual roster and its original PDF; `dictionary.csv` defines winner/candidate fields. Null means unavailable from the adopted source. Primary source records and the failed affidavit response remain in `data/raw/urban/patna/`.

From the repository root:

```sh
PYTHONPATH=src python -m local_elections_bihar.urban.parse_patna
PYTHONPATH=src python -m pytest -q tests/test_urban_patna.py
ruff check src/local_elections_bihar/urban tests/test_urban_patna.py
```

The parser builds offline, verifies retained input hashes, requires complete unique winner frames and preserves missing fields and conflicting values. The collector uses requests sessions, retries and retained ASP.NET form state; it can resume from receipts. No rural release is rebuilt.

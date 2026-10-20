# 2016 Mukhiya winner list (wcl.aspx)

The SEC's archived 2016 site has a second results form besides `ovc.aspx`, the
candidate-and-vote form behind `2016/seats.parquet`. The winner list
[`old-sec/wcl.aspx`](https://sec.bihar.gov.in/old-sec/wcl.aspx) takes post,
district and block. It returns one row per panchayat with the winner's name,
father/husband name, gender, age, category, education, mobile number, address
and the seat's reservation. It has no votes. Photos and affidavits sit behind
postbacks and were not collected.

It was collected for two sets of blocks:

- every block where `ovc.aspx` answered "Record not Found..!" for at least one
  Mukhiya seat, to see whether this list fills them;
- every block holding one of the Mukhiya seats whose `ovc.aspx` rows name no
  winner (`winner_note` set), as evidence for reviewing them.

## Findings

Collected 2026-10-19: 121 blocks, 1,682 listed rows. The 121 are the 120
target blocks plus the control block Ramgarhwa, 02/003.

- **It barely fills the gap.** It fills 8 of the 405 Mukhiya seats with no
  `ovc.aspx` record. All 11 blocks that are wholly missing (172 seats) answer
  "Record not Found..!" here too. In the 77 partly missing blocks, the list
  shows the seats `ovc.aspx` covered and 8 of the 233 it did not. Four of the
  eight are labelled unpadded here (`Jokihat/kakan/3`) but padded on the
  `ovc.aspx` page (`/03`).
- **It reads the same records as `ovc.aspx`.** Of 1,630 listed rows on seats
  with a `winners.parquet` winner, 1,628 name that winner verbatim. The two
  disagreements are source conflicts and are left as they are:
  - Motihari, Dhuru Lakhaura (02/011/03): the list names ANITA DEVI, but
    `ovc.aspx` gives her 2,226 votes against 2,291 for PRABHU SAHANI.
  - Chausa, Rasalpur Dhuriya (11/012/01): the list has two records, `/01`
    (USHA KUMARI, the `ovc.aspx` winner) and `/1` (SUNILA DEVI).
- **Seats with no derivable winner.** For the 41 seats whose `ovc.aspx` rows
  name no winner, `no_winner_review.csv` proposes 28 `supported` and 1
  `supported_if_same_person`. The other 12 are `undecided`: their outcome
  depends on whether repeated rows are partial counts or superseded entries.
- **Seat codes.** The number printed at the end of a seat label is not the
  frame code (Bisfi/Bhairva/17 is frame unit 19); 426 rows would land on the
  wrong seat if matched by it. Rows are matched by label to the `ovc.aspx`
  page, else by panchayat name (`match_basis`).

## Files

| File | Row | Key |
| --- | --- | --- |
| `winner_list_records.parquet` | Listed winner row | `district_code, block_code, unit_code, sr_no`; `unit_code` matches `2016/seats.parquet` |
| `coverage.csv` | Collected block | `district_code, block_code` |
| `comparison.csv` | Listed seat that also has a winner in `2016/winners.parquet` | seat key and `wcl_sr_no` |
| `no_winner_review.csv` | Seat with `winner_note` set | seat key |

`seat_label` keeps the printed text. `label_matches_frame` records whether the
printed panchayat name agrees with the frame label. Its one false row is
Ziradei code 10, which the frame uses for two panchayats.

A seat can have two rows (`unit_repeated`). The list reads the same records as
`ovc.aspx` and repeats their duplicates, so it is not an independent source for
the seats it covers.

`no_winner_review.csv` holds rule-based proposals, not reviewed decisions
(`review_status = unreviewed`). Rows are grouped into candidates by serial. A
candidate's floor is the lowest count among its rows. Its ceiling is the sum of
those rows, the reading in which repeated rows are partial counts to add. A
`supported` leader wins under any reading, and the winner list names the same
person. `winners.parquet` is unchanged.

## Reproduce

```sh
uv run python -m local_elections_bihar.year2016.collect_winner_list   # live, ~2.5 s between requests
make winner-list-2016
make verify-winner-list-2016
```

The collector writes one ledger per block to
`data/2016/raw/statewide/2016/winner_list/`, with every response body. These
ledgers are not yet in the Zenodo source archives. `MANIFEST.json` records
their checksums.

## Reviewed rulings

`no_winner_reviewed.csv` records the review of `no_winner_review.csv`
(2026-10-19). Rule: where the results page prints a candidate twice with
different counts, the winner is taken from the votes only when the leader's
lowest count exceeds every rival's counts added together. 29 seats are
accepted on that rule (28 `supported`, plus the Maniyari seat whose leader's
two rows differ only in the father's name, VIJAY/VINAY PASWAN); 12 are left
undecided. `winners.parquet` is unchanged; a consumer applies these rulings.

## Raw responses

The 121 winner-list responses (3 MB, gzipped JSON lines; sha256 in
`MANIFEST.json`) are committed under `data/2016/raw/statewide/2016/winner_list/`,
an exception to this repository's practice of archiving raw files on Zenodo:
they are small and were not part of the existing archives.

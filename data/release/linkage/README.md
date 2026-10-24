# Mukhiya seat links across elections

Research crosswalks between Mukhiya seats of the 2011, 2016 and 2021 general
elections. A link states that two GP names agree inside the same block. It does
not establish that boundaries are unchanged, and it is not an official identifier.

| File | Row | Key |
| --- | --- | --- |
| `mukhiya_2016_2021.parquet` | 2016 seat linked to a 2021 seat | `district_code, block_code, unit_code` and `unit_id_2021`, each unique |
| `mukhiya_2011_2016.parquet` | 2011 winner record linked to a 2016 seat | `record_id_2011` and the 2016 key, each unique |
| `place_transliterations.parquet` | Devanagari GP name and its romanization | `native` |

Join `mukhiya_2016_2021` to `release/2016/seats.parquet` on the 2016 key, and to the 2021
tables on `unit_id`. Join `mukhiya_2011_2016` to
`release/2011/mukhiya_reports/winner_records.parquet` on `record_id`.

## How the links are made

No GP identifier survives between elections. The 2016 form numbers GPs within a
block and prints romanized names. The 2021 portal uses district-wide panchayat ids
and Devanagari names. The 2011 reports print Devanagari GP names under romanized
block headings. District and block codes agree between 2016 and 2021. The 23
district names of the 2011 reports map to 2016 codes through a fixed table in the
code. Their 266 block headings map to 2016 block codes through the reviewed
[`data/manual/crosswalks/block_2011_2016.csv`](../../manual/crosswalks/block_2011_2016.csv). Some blocks
appear under two headings, e.g. `Pandaul` and `PANDAUL`, or `Chapra_Sadar` for
Chapra, so the map is many-to-one. Each row records a reason.

Devanagari names are romanized once with [indicate](https://pypi.org/project/indicate/)'s
local model, version recorded in `place_transliterations.json`. Names are folded
to absorb romanization variants: vowel length, `w`/`v`, aspiration, `sh`/`s`.
[preclink](https://pypi.org/project/preclink/) then pairs them within blocks by
optimal one-to-one assignment. Numbers, compass words and twin-village qualifiers
(Kalan, Khurd, Buzurg) are read from the printed name. `Dariyapur-1` never pairs
with `दरियापुर-2`, `uttar` never pairs with `dakshin`, and Kalan never pairs with
Khurd. A conflict needs both names to state something from the same family, so a
missing qualifier does not veto a pair.

The 2016–2021 link runs two passes:

- `link_pass = "name"` accepts a name score of at least 0.80.
- `link_pass = "name_and_wards"` runs on what remains. It requires the same
  number of ward seats in both years and a name score of at least 0.60.

## Checks

The ward count shares nothing with the name. Among name-pass links, the two years
agree on the ward count for 97.3% of GPs. Pairing GPs at random within the block
gives 23.9%. For 2011, a winner's exact name appears among the linked 2016 GP's
candidates 1.5% of the time, against 0.12% for a random GP in the block. Many 2011
incumbents could not stand again once 2016 reservations changed, so this check
confirms the link carries signal. It does not measure precision.

`MANIFEST.json` records input and output hashes, thresholds, package versions and
these checks. `make verify-linkage` re-checks hashes and one-to-one keys.

## What is not linked

- **2016–2021:** 455 of 8,400 2016 seats and 122 of 8,067 2021 seats remain
  unlinked. Two 2016 seats whose form code names two GPs (Siwan, Ziradei 10) are
  excluded.
- **2011–2016:** records with repeated seat labels are excluded. All 3,729
  remaining records have a reviewed block, and 3,342 are linked.

Unlinked rows are absent from the files, not matched to a null.

## Rebuild

```sh
uv sync --frozen --group transliterate      # only to redo the romanization
uv run python -m local_elections_bihar.linkage.mukhiya transliterate
make linkage
```

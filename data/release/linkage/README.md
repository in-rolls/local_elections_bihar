# Mukhiya seat links across elections

Research crosswalks between Mukhiya seats of the 2011, 2016 and 2021 general
elections, and between the two sources for 2006. A link states that two GP names
agree inside the same block (or, where marked, the same district). It does not
establish that boundaries are unchanged, and it is not an official identifier.

| File | Row | Key |
| --- | --- | --- |
| `mukhiya_2016_2021.parquet` | 2016 seat linked to a 2021 seat | `district_code, block_code, unit_code` and `unit_id_2021`, each unique |
| `mukhiya_2011_2016.parquet` | 2011 winner record linked to a 2016 seat | `record_id_2011` and the 2016 key, each unique |
| `mukhiya_2006_2016.parquet` | GP of M. R. Sharan's 2006 reservation file linked to a 2016 seat | `ugp` and the 2016 key, each unique |
| `mukhiya_2006_sharan.parquet` | GP of M. R. Sharan's 2006 reservation file linked to the GP of a 2006 mukhiya seat | `ugp` and `district, block, gram_panchayat`, each unique |
| `place_transliterations.parquet` | Devanagari GP name and its romanization | `native` |

Join `mukhiya_2016_2021` to `release/2016/seats.parquet` on the 2016 key, and to the 2021
tables on `unit_id`. Join `mukhiya_2011_2016` to
`release/2011/mukhiya_reports/winner_records.parquet` on `record_id`.

Join `mukhiya_2006_2016` to `release/2006/gp_head_reservations.parquet` on `ugp` and to
`release/2016/seats.parquet` on the 2016 key. That puts the 2006 reservation on the
codes the 2011 and 2021 links use, and it is the link to prefer.

Join `mukhiya_2006_sharan` to `release/2006/gp_head_reservations.parquet` on `ugp`, and
to the mukhiya rows of `release/2006/seats.parquet` on `district, block, gram_panchayat`.
The 2006 workbooks print some gram panchayats twice, so that join can return more than
one seat.

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

## Sharan's 2006 file

Sharan's file names gram panchayats in English, under blocks that are not always the
SEC's. It is linked twice: to the 2016 seats, and to the gram panchayats the 2006
mukhiya seats print.

Compass words differ between the sources: `ARER NORTH`, `PAROO [N]` and
`NORTHI PATJIRAWA` in Sharan's file, `Siswa Pashchimi` on the 2016 form, उत्तरी or उ0
in the 2006 workbooks. Each side's compass word is read into the key and removed from
the name before the names are compared.

Common names recur across a district's blocks, so each link runs in three steps:

- A first pass over whole districts only learns which block of one source each block
  of the other mostly falls in. Its pairs are discarded.
- `link_pass = "block"` pairs names inside that block, at a name score of at least 0.80.
- `link_pass = "district"` pairs what is left across the district, with no block to
  guard the pair.

To 2016, both sides are in Latin letters and 7,797 of 7,809 links are made inside a
block. To the 2006 seats, the Devanagari names are romanized first, and 440 links are
district-pass: East Champaran and Jamui, whose 2006 workbooks do not separate blocks,
account for most of them.

## Checks

The ward count shares nothing with the name. Among name-pass links, the two years
agree on the ward count for 97.3% of GPs. Pairing GPs at random within the block
gives 23.9%. For 2011, a winner's exact name appears among the linked 2016 GP's
candidates 1.5% of the time, against 0.12% for a random GP in the block. Many 2011
incumbents could not stand again once 2016 reservations changed, so this check
confirms the link carries signal. It does not measure precision.

For Sharan's file the check is the reservation, which plays no part in the link.
Section 4 of the Bihar Panchayat Raj (Amendment) Act, 2009 rotates a mukhiya seat's
reservation only after two consecutive general elections, counted from 2006, so a
2006 gram panchayat should carry its 2011 label. Through `mukhiya_2006_2016` and
`mukhiya_2011_2016`, Sharan's 2006 women's flag equals the printed 2011 label for
98.0% of 2,212 gram panchayats; pairing them at random gives 50.0%. The caste
reservation agrees for 98.1% of 2,520, against 54.5%. The 2011 reports cover 23
districts and print a women's label in only some.

For the link to the 2006 seats, only Madhubani's result notices state a 2006 mukhiya reservation officially. Of 343
linked Madhubani pairs, 96.5% carry the same caste and woman reservation in both
sources, counting the notices' पिछड़ा वर्ग as Sharan's EBC. Pairing the same gram
panchayats at random gives 25.8%. A disagreement can be a wrong link or the two
sources differing, and the check cannot tell which. It also covers one district.

`MANIFEST.json` records input and output hashes, thresholds, package versions and
these checks. `make verify-linkage` re-checks hashes and one-to-one keys.

## What is not linked

- **2016–2021:** 455 of 8,400 2016 seats and 122 of 8,067 2021 seats remain
  unlinked. Two 2016 seats whose form code names two GPs (Siwan, Ziradei 10) are
  excluded.
- **2011–2016:** records with repeated seat labels are excluded. All 3,729
  remaining records have a reviewed block, and 3,342 are linked.

- **2006–2016:** 7,809 of Sharan's 8,262 gram panchayats are linked to the 8,400
  2016 seats.
- **2006, Sharan:** 6,954 of Sharan's 8,262 gram panchayats are linked to the 7,895
  that the 2006 mukhiya seats print. The 2006 workbooks are short in some districts
  (Begusarai prints 107 seats against Sharan's 217), which caps the link there.

Unlinked rows are absent from the files, not matched to a null.

## Rebuild

```sh
# Only to romanize names a new source adds. Earlier readings are kept, and the run
# refuses an indicate other than the one recorded in place_transliterations.json.
uv run --group transliterate --with "indicate==0.10.0" \
  python -m local_elections_bihar.linkage.mukhiya transliterate
make linkage
```

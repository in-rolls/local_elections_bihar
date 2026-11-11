"""Link Mukhiya seats across the 2011, 2016 and 2021 general elections.

No source carries a GP identifier that survives between elections: 2016 numbers
GPs within a block and prints romanized names, 2021 uses district-wide panchayat
ids and Devanagari names, and the 2011 district reports print Devanagari GP names
under romanized block headings. District and block codes do agree between 2016
and 2021, so GPs are linked by name inside a block.

Devanagari names are romanized once with indicate's local model and kept in
`place_transliterations.parquet`, so the link can be rebuilt without PyTorch.
Matching uses preclink: block on district and block, score folded names, and take
the optimal one-to-one assignment. Numbers and compass words in a name ("-2",
"uttar") distinguish sibling GPs that otherwise share a name, so a pair whose
numbers or directions disagree scores zero.

The 2016-2021 link runs two passes. The first accepts names alone. The second,
on what is left, also requires the same number of wards, an attribute that shares
nothing with the name. Ward agreement among first-pass pairs is reported as the
check on the name match and is not used to make those pairs.
"""

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import pandas as pd
import polars as pl
from preclink import ExactComparison, Pipeline
from rapidfuzz import fuzz

DATA = Path("data")
OUT = DATA / "release" / "linkage"
TRANSLITERATIONS = OUT / "place_transliterations.parquet"
BLOCKS_2011 = DATA / "manual" / "crosswalks" / "block_2011_2016.csv"
INPUTS = {
    "seats_2016": DATA / "release/2016/seats.parquet",
    "seats_2021": DATA / "release/2021/seats.parquet",
    "reservations_2021": DATA / "release/2021/term_feed_reservations.parquet",
    "winners_2011": DATA / "release/2011/mukhiya_reports/winner_records.parquet",
    "seats_2006": DATA / "release/2006/seats.parquet",
    "sharan_2006": DATA / "release/2006/gp_head_reservations.parquet",
}
NAME_THRESHOLD = 0.80
# With equal weights on name and ward count, 0.80 means the ward counts agree
# and the name scores at least 0.60.
WARD_PASS_THRESHOLD = 0.80
# Every district the 2011 reports cover, spelled as the reports print it.
DISTRICTS_2011 = {
    "Aurangabad": "35",
    "BEGUSARAI": "20",
    "BHAGALPUR": "22",
    "BHOJPUR": "29",
    "BUXAR": "30",
    "GAYA": "36",
    "GOPALGANJ": "15",
    "JAMUI": "38",
    "JEHANABAD": "34",
    "KAIMUR": "31",
    "KATIHAR": "10",
    "KHAGARIA": "21",
    "KISHANGANJ": "08",
    "Lakhisaray": "25",
    "MADHUBANI": "05",
    "NALANDA": "27",
    "PATNA": "28",
    "ROHTAS": "32",
    "SAHARSA": "12",
    "SAMASTIPUR": "19",
    "SARAN": "17",
    "SIWAN": "16",
    "W.CHAMPARAN": "01",
}
FOLDS = [
    (r"[^a-z]", ""),
    (r"aa+", "a"),
    (r"ee+|ii+", "i"),
    (r"oo+|uu+", "u"),
    (r"w", "v"),
    (r"z", "j"),
    (r"ph", "f"),
    (r"q", "k"),
    (r"([bcdgjkpt])h", r"\1"),
    (r"sh", "s"),
    (r"rh", "r"),
    (r"y", "i"),
    (r"(.)\1", r"\1"),
]
DIRECTIONS = {
    "east": r"purv|poorv|पूर्व|पूरब|purab",
    "west": r"pash?chim|pachim|पश्चिम|पच्छिम",
    "north": r"uttar|utter|उत्\s*तर|उतर",
    "south": r"daksh[ai]n|dakchhin|dakhin|दक्षिण|दक्षिनी|दछिन",
    # Twin villages are distinguished by these; "Kalan" is not "Khurd".
    "kalan": r"\bkal[ae]?n\b|\bkalaan\b|कलां|कला\b",
    "khurd": r"\bkhurd\b|\bkhurad\b|खुर्द",
    "buzurg": r"\bbuzurg\b|\bbujurg\b|बुजुर्ग|बुज़ुर्ग",
}
# Sharan's file names its districts in English; the 2006 workbooks in Hindi.
DISTRICTS_SHARAN = {
    "ARARIA": "अररिया",
    "ARWAL": "अरवल",
    "AURANGABAD": "औरंगाबाद",
    "BANKA": "बांका",
    "BEGUSARAI": "बेगुसराय",
    "BHAGALPUR": "भागलपुर",
    "BHOJPUR": "भोजपुर",
    "BUXAR": "बक्सर",
    "DARBHANGA": "दरभंगा",
    "GAYA": "गया",
    "GOPALGANJ": "गोपालगंज",
    "JAMUI": "जमुई",
    "JEHANABAD": "जहानाबाद",
    "KAIMUR (BHABUA)": "कैमूर",
    "KATIHAR": "कटिहार",
    "KHAGARIA": "खगडिया",
    "KISHANGANJ": "किशनगंज",
    "LAKHISARAI": "लखीसराय",
    "MADHEPURA": "मधेपुरा",
    "MADHUBANI": "मधुबनी",
    "MUNGER": "मुंगेर",
    "MUZAFFARPUR": "मुजफ्फरपुर",
    "NALANDA": "नालन्दा",
    "NAWADA": "नवादा",
    "PASHCHIM CHAMPARAN": "बेतिया",
    "PATNA": "पटना",
    "PURBI CHAMPARAN": "पूर्वी चम्पारण",
    "PURNIA": "पूर्णिया",
    "ROHTAS": "रोहतास",
    "SAHARSA": "सहरसा",
    "SAMASTIPUR": "समस्तीपुर",
    "SARAN": "सारण",
    "SHEIKHPURA": "शेखपुरा",
    "SHEOHAR": "शिवहर",
    "SITAMARHI": "सीतामढ़ी",
    "SIWAN": "सिवान",
    "SUPAUL": "सुपौल",
    "VAISHALI": "वैशाली",
}
# The same districts under the codes the 2016 form uses.
DISTRICT_CODES_SHARAN = {
    "ARARIA": "07",
    "ARWAL": "33",
    "AURANGABAD": "35",
    "BANKA": "23",
    "BEGUSARAI": "20",
    "BHAGALPUR": "22",
    "BHOJPUR": "29",
    "BUXAR": "30",
    "DARBHANGA": "13",
    "GAYA": "36",
    "GOPALGANJ": "15",
    "JAMUI": "38",
    "JEHANABAD": "34",
    "KAIMUR (BHABUA)": "31",
    "KATIHAR": "10",
    "KHAGARIA": "21",
    "KISHANGANJ": "08",
    "LAKHISARAI": "25",
    "MADHEPURA": "11",
    "MADHUBANI": "05",
    "MUNGER": "24",
    "MUZAFFARPUR": "14",
    "NALANDA": "27",
    "NAWADA": "37",
    "PASHCHIM CHAMPARAN": "01",
    "PATNA": "28",
    "PURBI CHAMPARAN": "02",
    "PURNIA": "09",
    "ROHTAS": "32",
    "SAHARSA": "12",
    "SAMASTIPUR": "19",
    "SARAN": "17",
    "SHEIKHPURA": "26",
    "SHEOHAR": "03",
    "SITAMARHI": "04",
    "SIWAN": "16",
    "SUPAUL": "06",
    "VAISHALI": "18",
}
# Sharan's file writes compass words in English ("ARER NORTH", "PAROO [N]",
# even "NORTHI" for उत्तरी) where the 2006 workbooks print the Hindi word or its
# abbreviation (उ0). Each side's word is read into the key and taken out of the
# name, so the rest of the name is compared like with like.
COMPASS_ENGLISH = {
    "east": r"\beast[i]?\b|\bpoorav\b|[\[(]\s*e\s*[\])]",
    "west": r"\bwest[i]?\b|[\[(]\s*w\s*[\])]",
    "north": r"\bnorth[i]?\b|[\[(]\s*n\s*[\])]",
    "south": r"\bsouth[i]?\b|[\[(]\s*s\s*[\])]",
    "middle": r"\bmiddle\b",
}
COMPASS_HINDI = {
    "east": r"पूर्वी?|पूरबी?|पू0",
    "west": r"पश्चिमी?|पच्छिमी?|प0",
    "north": r"उत्\s*तर[ीा]?|उतर[ी]?|उ0",
    "south": r"दक्षिण[ी]?|दक्षिनी|दछिन|द0",
    "middle": r"मध्य",
}
COMPASS_WORD = re.compile("|".join(COMPASS_HINDI.values()))
# Used only when the romanization does not keep the print's word boundaries.
COMPASS_LATIN = re.compile(
    r"\b(p[uo]+rv[ia]?|purabi?|pash?chh?im[ia]?|pachh?imi?|utt?[ae]r[ia]?"
    r"|daksh[ai]n[ia]?|dakchhin|dakhin|madhya)\b"
)
COMPASS_ROMANIZED = {
    "east": r"\bp[uo]+rv[ia]?\b|\bpurabi?\b",
    "west": r"\bpash?chh?im[ia]?\b|\bpachh?imi?\b",
    "north": r"\butt?[ae]r[ia]?\b",
    "south": r"\bdaksh[ai]n[ia]?\b|\bdakchhin\b|\bdakhin\b",
    "middle": r"\bmadhya\b",
}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
CODE_PREFIX = re.compile(r"^\s*\d+\s*-\s*")


# A name may state a direction, a twin-village qualifier, both or neither. Two
# names conflict only when both state one from the same family and they differ.
QUALIFIER_FAMILIES = (
    frozenset({"east", "west", "north", "south", "middle"}),
    frozenset({"kalan", "khurd", "buzurg", "khas"}),
)


def qualifiers_conflict(a, b):
    return any((a & f) and (b & f) and (a & f) != (b & f) for f in QUALIFIER_FAMILIES)


def fold(name):
    """Collapse spellings that romanizations of one Hindi name differ by."""
    text = CODE_PREFIX.sub("", name or "").lower()
    for pattern, replacement in FOLDS:
        text = re.sub(pattern, replacement, text)
    return text


def name_key(native, latin):
    """Folded romanized name, with numbers and directions read from the printed
    name: the transliterator does not reliably keep digits."""
    printed = CODE_PREFIX.sub("", native or "").translate(DIGITS).lower()
    numbers = frozenset(int(n) for n in re.findall(r"\d+", printed))
    directions = frozenset(d for d, p in DIRECTIONS.items() if re.search(p, printed))
    return fold(latin), numbers, directions


def twins(text):
    return frozenset(
        d for d in ("kalan", "khurd", "buzurg") if re.search(DIRECTIONS[d], text)
    )


def english_key(name):
    """`name_key` for a name printed in English, as in Sharan's file."""
    text = name.lower()
    compass = frozenset(d for d, p in COMPASS_ENGLISH.items() if re.search(p, text))
    for pattern in COMPASS_ENGLISH.values():
        text = re.sub(pattern, " ", text)
    numbers = {int(n) for n in re.findall(r"\d+", text)}
    numbers |= {ROMAN[n] for n in re.findall(r"[-\s](i{1,3}|iv)\s*$", text)}
    text = re.sub(r"[-\s](i{1,3}|iv)\s*$", " ", text)
    return fold(text), frozenset(numbers), compass | twins(text)


def romanized_key(name):
    """`name_key` for a Hindi name printed in Latin letters, as on the 2016
    form ("SINGHIYA BUJURG DAKSHANI"), with the compass word taken out of the
    name so it meets `english_key`. A form may also use the English word."""
    text = CODE_PREFIX.sub("", name).lower()
    compass = frozenset(
        d
        for d in COMPASS_ENGLISH
        if re.search(COMPASS_ENGLISH[d], text) or re.search(COMPASS_ROMANIZED[d], text)
    )
    for pattern in (*COMPASS_ENGLISH.values(), *COMPASS_ROMANIZED.values()):
        text = re.sub(pattern, " ", text)
    numbers = frozenset(int(n) for n in re.findall(r"\d+", text))
    return fold(text), numbers, compass | twins(text)


def hindi_key(native, latin):
    """`name_key` for a Devanagari name, with its compass word read from the
    print and taken out of the romanization to match `english_key`. The model
    romanizes an abbreviation unpredictably (प0 as "0v"), so the word is
    dropped by its position in the name wherever the words line up."""
    printed = native.translate(DIGITS)
    compass = frozenset(d for d, p in COMPASS_HINDI.items() if re.search(p, printed))
    numbers = frozenset(
        int(n) for n in re.findall(r"\d+", COMPASS_WORD.sub(" ", printed)) if int(n)
    )
    words, romanized = printed.split(), latin.lower().split()
    if len(words) == len(romanized):
        stem = " ".join(
            r
            for w, r in zip(words, romanized, strict=True)
            if not COMPASS_WORD.fullmatch(w)
        )
    else:
        stem = latin.lower()
    return fold(COMPASS_LATIN.sub(" ", stem)), numbers, compass | twins(printed)


def similarity(a, b):
    """Name similarity in [0, 1]; the consonant skeleton forgives vowel
    spellings at a small cost."""
    if not a or not b:
        return 0.0
    skeleton = fuzz.ratio(re.sub("[aeiou]", "", a), re.sub("[aeiou]", "", b)) - 5
    return max(fuzz.ratio(a, b), skeleton) / 100


@dataclass(frozen=True, slots=True)
class PlaceName:
    """preclink comparison on `name_key` tuples."""

    column: str = "name_key"
    weight: float = 1.0

    def compare(self, left, right):
        scores = []
        for (a, a_num, a_dir), (b, b_num, b_dir) in zip(left, right, strict=True):
            conflict = (a_num and b_num and a_num != b_num) or qualifiers_conflict(
                a_dir, b_dir
            )
            scores.append(0.0 if conflict else similarity(a, b))
        return pd.Series(scores, index=left.index)


def link(left, right, block, comparisons, threshold):
    """Optimal one-to-one pairs within blocks, run one district at a time so the
    assignment matrix stays the size of a district."""
    pipeline = (
        Pipeline()
        .block(on=block)
        .score(comparisons=comparisons)
        .filter(min_score=threshold)
        .decide(method="hungarian")
        .build()
    )
    found = []
    for district in sorted(set(left["district_code"]) & set(right["district_code"])):
        lg = left[left["district_code"] == district].reset_index(drop=True)
        rg = right[right["district_code"] == district].reset_index(drop=True)
        matches = pipeline.link(lg, rg).matches
        if matches.empty:
            continue
        found.append(
            pd.DataFrame(
                {
                    "left": lg.loc[matches["left_index"], "key"].to_numpy(),
                    "right": rg.loc[matches["right_index"], "key"].to_numpy(),
                    "name_score": matches["name_key_score"].to_numpy(),
                }
            )
        )
    if not found:
        return pd.DataFrame(columns=["left", "right", "name_score"])
    return pd.concat(found, ignore_index=True)


def transliterations(path=TRANSLITERATIONS):
    return dict(pl.read_parquet(path).select("native", "latin").iter_rows())


def generator(path=TRANSLITERATIONS):
    return json.loads(path.with_suffix(".json").read_text())["generator"]


def transliteration_method(path=TRANSLITERATIONS):
    """What produced the romanizations, e.g. "indicate 0.10.0 model" (NAMING.md
    asks every *_latin value to say how it was made)."""
    info = generator(path)
    return f"indicate {info['indicate']} {info['engine']}"


def method_beside(column):
    return (
        pl.when(pl.col(column).is_not_null())
        .then(pl.lit(transliteration_method()))
        .alias(column.replace("gp_latin", "gp_latin_method"))
    )


def gps_2016():
    """2016 Mukhiya seats. Seats whose form code names two places (Siwan,
    Ziradei 10) cannot be tied to one results page and are left unlinked."""
    seats = pl.read_parquet(INPUTS["seats_2016"]).filter(~pl.col("code_repeated"))
    wards = (
        seats.filter(pl.col("office") == "ward_member")
        .group_by("district_code", "block_code", "panchayat_code")
        .agg(wards=pl.len())
        .rename({"panchayat_code": "unit_code"})
    )
    return (
        seats.filter(pl.col("office") == "mukhiya")
        .join(wards, on=["district_code", "block_code", "unit_code"], how="left")
        .with_columns(
            key=pl.concat_str(
                "district_code", "block_code", "unit_code", separator="_"
            ),
            name=pl.col("unit").str.replace(CODE_PREFIX.pattern, ""),
        )
    )


def gps_2021(translit):
    seats = pl.read_parquet(INPUTS["seats_2021"])
    wards = (
        seats.filter(pl.col("post_id") == 1)
        .group_by("district_id", "block_id", "panchayat_id")
        .agg(wards=pl.len())
    )
    return (
        pl.read_parquet(INPUTS["reservations_2021"])
        .filter(pl.col("post_id") == 3)
        .join(wards, on=["district_id", "block_id", "panchayat_id"], how="left")
        .with_columns(
            key=pl.col("unit_id"),
            district_code=pl.col("district_id").cast(pl.String).str.zfill(2),
            block_code=pl.col("block_id").cast(pl.String).str.zfill(3),
            name=pl.col("panchayat"),
            latin=pl.col("panchayat").replace_strict(translit, default=None),
        )
    )


def frame(gps, native, latin):
    columns = [c for c in ("key", "district_code", "block_code", "wards") if c in gps]
    out = gps.select(columns).to_pandas()
    out["name_key"] = [
        name_key(n, r)
        for n, r in zip(gps[native].to_list(), gps[latin].to_list(), strict=True)
    ]
    return out


def link_2016_2021(translit):
    g16, g21 = gps_2016(), gps_2021(translit)
    left, right = frame(g16, "name", "name"), frame(g21, "name", "latin")
    block = ["district_code", "block_code"]
    first = link(left, right, block, [PlaceName()], NAME_THRESHOLD).assign(
        link_pass="name"
    )
    rest_l = left[~left["key"].isin(first["left"])]
    rest_r = right[~right["key"].isin(first["right"])]
    second = link(
        rest_l,
        rest_r,
        block,
        [PlaceName(), ExactComparison("wards")],
        WARD_PASS_THRESHOLD,
    ).assign(link_pass="name_and_wards")
    pairs = pl.from_pandas(pd.concat([first, second], ignore_index=True))
    pairs = pairs.with_columns(
        pl.when(pl.col("link_pass") == "name_and_wards")
        .then(None)
        .otherwise(pl.col("name_score"))
        .alias("name_score_first_pass")
    )
    out = (
        pairs.rename({"left": "key_2016", "right": "unit_id_2021"})
        .join(
            g16.select(
                pl.col("key").alias("key_2016"),
                "district_code",
                "block_code",
                "unit_code",
                pl.col("name").alias("gp_2016"),
                pl.col("wards").alias("wards_2016"),
            ),
            on="key_2016",
        )
        .join(
            g21.select(
                pl.col("key").alias("unit_id_2021"),
                "panchayat_id",
                pl.col("name").alias("gp_2021"),
                pl.col("latin").alias("gp_latin_2021"),
                pl.col("wards").alias("wards_2021"),
            ),
            on="unit_id_2021",
        )
        .select(
            "district_code",
            "block_code",
            "unit_code",
            "unit_id_2021",
            "panchayat_id",
            "gp_2016",
            "gp_2021",
            "gp_latin_2021",
            method_beside("gp_latin_2021"),
            "wards_2016",
            "wards_2021",
            "name_score",
            "link_pass",
        )
        .sort("district_code", "block_code", "unit_code")
    )
    first_pass = out.filter(pl.col("link_pass") == "name")
    agree = (first_pass["wards_2016"] == first_pass["wards_2021"]).mean()
    shuffled = first_pass.with_columns(
        pl.col("wards_2021").shuffle(seed=1).over("district_code", "block_code")
    )
    placebo = (shuffled["wards_2016"] == shuffled["wards_2021"]).mean()
    checks = {
        "gps_2016": g16.height,
        "gps_2021": g21.height,
        "linked": out.height,
        "linked_by_name": first_pass.height,
        "linked_by_name_and_wards": out.height - first_pass.height,
        "unlinked_2016": g16.height - out.height,
        "unlinked_2021": g21.height - out.height,
        "ward_count_agreement_name_pass": round(agree, 4),
        "ward_count_agreement_shuffled_within_block": round(placebo, 4),
    }
    return out, checks


def blocks_2011():
    """2011 block headings to 2016 block codes, from the reviewed crosswalk. A
    block can appear under two headings in one report, so the map is many to one."""
    return (
        pl.read_csv(
            BLOCKS_2011,
            schema_overrides={"district_code": pl.String, "block_code_2016": pl.String},
        )
        .filter(pl.col("decision") == "linked")
        .select(
            pl.concat_str("district_code", "block_2011", separator="|").alias(
                "block_key"
            ),
            pl.col("block_code_2016").alias("block_code"),
            pl.col("name_score").alias("block_score"),
        )
    )


def link_2011_2016(translit):
    g16 = gps_2016()
    w11 = (
        pl.read_parquet(INPUTS["winners_2011"])
        .filter(~pl.col("seat_label_repeated"))
        .with_columns(
            district_code=pl.col("district_raw").replace_strict(DISTRICTS_2011),
            latin=pl.col("panchayat_raw").replace_strict(translit, default=None),
        )
    )
    blocks = blocks_2011()
    w11 = w11.with_columns(
        block_key=pl.concat_str("district_code", "block_raw", separator="|")
    ).join(blocks, on="block_key", how="left")
    located = w11.filter(pl.col("block_code").is_not_null())
    left = frame(
        located.with_columns(key=pl.col("record_id"), wards=pl.lit(None)),
        "panchayat_raw",
        "latin",
    )
    right = frame(g16, "name", "name")
    pairs = pl.from_pandas(
        link(
            left, right, ["district_code", "block_code"], [PlaceName()], NAME_THRESHOLD
        )
    )
    out = (
        pairs.rename({"left": "record_id_2011", "right": "key_2016"})
        .join(
            located.select(
                pl.col("record_id").alias("record_id_2011"),
                pl.col("block_raw").alias("block_2011"),
                pl.col("panchayat_raw").alias("gp_2011"),
                pl.col("latin").alias("gp_latin_2011"),
                "block_score",
            ),
            on="record_id_2011",
        )
        .join(
            g16.select(
                pl.col("key").alias("key_2016"),
                "district_code",
                "block_code",
                "unit_code",
                pl.col("name").alias("gp_2016"),
            ),
            on="key_2016",
        )
        .select(
            "record_id_2011",
            "district_code",
            "block_code",
            "unit_code",
            "block_2011",
            "gp_2011",
            "gp_latin_2011",
            method_beside("gp_latin_2011"),
            "gp_2016",
            "block_score",
            "name_score",
        )
        .sort("district_code", "block_code", "unit_code")
    )
    checks = {
        "records_2011": pl.read_parquet(INPUTS["winners_2011"]).height,
        "records_2011_unrepeated_labels": w11.height,
        "records_2011_block_located": located.height,
        "block_headings_2011": w11["block_key"].n_unique(),
        "block_headings_linked": blocks.height,
        "linked": out.height,
    }
    return out, checks


def gps_2006():
    """Gram panchayats of the 2006 mukhiya seats, one row per printed
    (district, block, gram_panchayat): the workbooks repeat some and number
    seats only within a sheet, so the names are the only handle."""
    return (
        pl.read_parquet(INPUTS["seats_2006"])
        .filter(
            (pl.col("office") == "mukhiya") & pl.col("gram_panchayat").is_not_null()
        )
        .select("district", "block", "gram_panchayat")
        .unique(maintain_order=True)
        .with_row_index("key")
    )


def link_in_learned_blocks(coded, free):
    """Pair two lists of gram panchayats that divide a district into blocks
    differently. `coded` carries `block_code`; `free` carries its own
    `block_name` (possibly missing). Common names recur across a district's
    blocks, so a first pass over whole districts is used only to learn which
    coded block each of `free`'s blocks mostly falls in. `link_pass = "block"`
    then pairs names inside that block, and `link_pass = "district"` pairs
    what is left across the district."""
    comparisons = [PlaceName()]
    scout = (
        link(coded, free, ["district_code"], comparisons, NAME_THRESHOLD)
        .merge(coded[["key", "block_code"]], left_on="left", right_on="key")
        .merge(
            free[["key", "district_code", "block_name"]],
            left_on="right",
            right_on="key",
        )
    )
    votes = (
        scout.dropna(subset=["block_name"])
        .groupby(["district_code", "block_name"])["block_code"]
        .agg(lambda blocks: blocks.mode().iloc[0])
    )
    free = free.assign(
        block_code=[
            votes.get((d, b))
            for d, b in zip(free["district_code"], free["block_name"], strict=True)
        ]
    )
    first = link(
        coded,
        free.dropna(subset=["block_code"]),
        ["district_code", "block_code"],
        comparisons,
        NAME_THRESHOLD,
    ).assign(link_pass="block")
    second = link(
        coded[~coded["key"].isin(first["left"])],
        free[~free["key"].isin(first["right"])].drop(columns="block_code"),
        ["district_code"],
        comparisons,
        NAME_THRESHOLD,
    ).assign(link_pass="district")
    return pl.from_pandas(pd.concat([first, second], ignore_index=True))


def agreement(table, ours, theirs):
    """Share of rows where two columns agree, beside what pairing the same
    rows at random would give."""
    a = table.group_by(pl.col(ours).alias("v")).agg(a=pl.len())
    b = table.group_by(pl.col(theirs).alias("v")).agg(b=pl.len())
    chance = (
        a.join(b, on="v").select((pl.col("a") * pl.col("b")).sum()).item()
        / table.height**2
    )
    same = table.select((pl.col(ours) == pl.col(theirs)).mean()).item()
    return round(same, 4), round(chance, 4)


def link_2006_2016(links_2011):
    """Sharan's 2006 gram panchayats to the 2016 seats, which carry the codes
    the 2011 and 2021 links hang on. Both sides print names in Latin letters.

    The check is the 2011 reservation, which plays no part in the link: Bihar
    held a seat's reservation for two elections, so a 2006 gram panchayat
    should carry its 2011 label. `links_2011` supplies the 2011 record of a
    2016 seat."""
    sharan = pl.read_parquet(INPUTS["sharan_2006"])
    g16 = gps_2016()
    coded = pd.DataFrame(
        {
            "key": g16["key"].to_list(),
            "district_code": g16["district_code"].to_list(),
            "block_code": g16["block_code"].to_list(),
            "name_key": [romanized_key(n) for n in g16["name"]],
        }
    )
    free = pd.DataFrame(
        {
            "key": sharan["ugp"].to_list(),
            "district_code": [DISTRICT_CODES_SHARAN[d] for d in sharan["district"]],
            "block_name": sharan["block"].to_list(),
            "name_key": [english_key(n) for n in sharan["gram_panchayat"]],
        }
    )
    pairs = link_in_learned_blocks(coded, free).with_columns(
        pl.col("right").cast(pl.Int32)
    )
    out = (
        pairs.rename({"left": "key", "right": "ugp"})
        .join(
            g16.select(
                "key",
                "district_code",
                "block_code",
                "unit_code",
                pl.col("name").alias("gp_2016"),
            ),
            on="key",
        )
        .join(
            sharan.select(
                "ugp",
                pl.col("district").alias("district_sharan"),
                pl.col("block").alias("block_sharan"),
                pl.col("gram_panchayat").alias("gp_sharan"),
                "reserved_caste",
                "reserved_woman",
            ),
            on="ugp",
        )
        .sort("ugp")
    )
    printed = (
        out.join(
            links_2011.select(
                "record_id_2011", "district_code", "block_code", "unit_code"
            ),
            on=["district_code", "block_code", "unit_code"],
        )
        .join(
            pl.read_parquet(INPUTS["winners_2011"]).select(
                pl.col("record_id").alias("record_id_2011"),
                pl.col("reserved_woman").alias("woman_2011"),
                # 2011 prints the backward-class seats BC or EBC by district.
                pl.col("reserved_caste")
                .replace({"unreserved": "NONE", "BC": "EBC"})
                .alias("caste_2011"),
            ),
            on="record_id_2011",
        )
        .with_columns(pl.col("reserved_woman").cast(pl.Int64))
    )
    women = printed.filter(pl.col("woman_2011").is_not_null()).with_columns(
        pl.col("woman_2011").cast(pl.Int64)
    )
    caste = printed.filter(pl.col("caste_2011").is_not_null())
    woman_same, woman_chance = agreement(women, "reserved_woman", "woman_2011")
    caste_same, caste_chance = agreement(caste, "reserved_caste", "caste_2011")
    checks = {
        "gps_sharan": sharan.height,
        "gps_2016": g16.height,
        "linked": out.height,
        "linked_block_pass": out.filter(pl.col("link_pass") == "block").height,
        "linked_district_pass": out.filter(pl.col("link_pass") == "district").height,
        "with_2011_woman_label": women.height,
        "woman_agreement_2006_2011": woman_same,
        "woman_agreement_random_pairing": woman_chance,
        "woman_agreement_2006_2011_block_pass": agreement(
            women.filter(pl.col("link_pass") == "block"),
            "reserved_woman",
            "woman_2011",
        )[0],
        "with_2011_caste_label": caste.height,
        "caste_agreement_2006_2011": caste_same,
        "caste_agreement_random_pairing": caste_chance,
    }
    return (
        out.select(
            "ugp",
            "district_code",
            "block_code",
            "unit_code",
            "district_sharan",
            "block_sharan",
            "gp_sharan",
            "gp_2016",
            "name_score",
            "link_pass",
        ),
        checks,
    )


def link_2006_sharan(translit):
    """Sharan's English-named gram panchayats to the 2006 mukhiya seats' own.

    The two sources do not divide a district into the same blocks (Sharan's
    Jainagar has 13 gram panchayats, the SEC's 15), and common names recur
    across a district's blocks. So a first pass over whole districts is used
    only to learn which of Sharan's blocks each SEC block mostly falls in;
    `link_pass = "block"` then pairs names inside that block, and
    `link_pass = "district"` pairs what is left across the district.
    """
    sharan = pl.read_parquet(INPUTS["sharan_2006"])
    seats = gps_2006()
    if set(seats["district"]) != set(DISTRICTS_SHARAN.values()):
        raise ValueError("2006 districts differ from the fixed table")
    code = {hindi: english for english, hindi in DISTRICTS_SHARAN.items()}
    left = pd.DataFrame(
        {
            "key": sharan["ugp"].to_list(),
            "district_code": sharan["district"].to_list(),
            "block_code": sharan["block"].to_list(),
            "name_key": [english_key(n) for n in sharan["gram_panchayat"]],
        }
    )
    right = pd.DataFrame(
        {
            "key": seats["key"].to_list(),
            "district_code": [code[d] for d in seats["district"]],
            "block_name": seats["block"].to_list(),
            "name_key": [hindi_key(n, translit[n]) for n in seats["gram_panchayat"]],
        }
    )
    pairs = link_in_learned_blocks(left, right).with_columns(
        pl.col("left").cast(pl.Int32), pl.col("right").cast(pl.UInt32)
    )
    out = (
        pairs.join(
            sharan.select(
                pl.col("ugp").alias("left"),
                pl.col("district").alias("district_sharan"),
                pl.col("block").alias("block_sharan"),
                pl.col("gram_panchayat").alias("gp_sharan"),
                pl.col("reserved_caste").alias("caste_sharan"),
                pl.col("reserved_woman").alias("woman_sharan"),
            ),
            on="left",
        )
        .join(seats.rename({"key": "right"}), on="right")
        .with_columns(
            gp_latin=pl.col("gram_panchayat").replace_strict(translit, default=None)
        )
        .rename({"left": "ugp"})
        .sort("ugp")
    )
    checks = {
        "gps_sharan": sharan.height,
        "gps_2006": seats.height,
        "linked": out.height,
        "linked_block_pass": out.filter(pl.col("link_pass") == "block").height,
        "linked_district_pass": out.filter(pl.col("link_pass") == "district").height,
        **notice_agreement(out),
    }
    return (
        out.select(
            "ugp",
            "district_sharan",
            "block_sharan",
            "gp_sharan",
            "district",
            "block",
            "gram_panchayat",
            "gp_latin",
            method_beside("gp_latin"),
            "name_score",
            "link_pass",
        ),
        checks,
    )


def notice_agreement(links):
    """Does a linked pair carry the same reservation in both sources? Only
    Madhubani's result notices state a mukhiya reservation officially, and the
    reservation plays no part in making the link. The notices' पिछड़ा वर्ग (BC)
    is compared with Sharan's EBC. The baseline is what pairing the same two
    sets of gram panchayats at random would give."""
    official = (
        pl.read_parquet(INPUTS["seats_2006"])
        .filter(
            (pl.col("office") == "mukhiya")
            & (pl.col("source_document") == "result_notice")
            & pl.col("reserved_caste").is_not_null()
            & pl.col("reserved_woman").is_not_null()
        )
        .group_by("district", "block", "gram_panchayat")
        .agg(
            pl.col("reserved_caste").n_unique().alias("readings"),
            pl.col("reserved_caste").first().replace("BC", "EBC").alias("caste"),
            pl.col("reserved_woman").first().alias("woman"),
            pl.col("reserved_woman").n_unique().alias("woman_readings"),
        )
        .filter((pl.col("readings") == 1) & (pl.col("woman_readings") == 1))
    )
    both = links.join(official, on=["district", "block", "gram_panchayat"])
    same = (pl.col("caste") == pl.col("caste_sharan")) & (
        pl.col("woman") == pl.col("woman_sharan")
    )
    ours = both.group_by("caste", "woman").agg(a=pl.len())
    theirs = both.group_by(
        pl.col("caste_sharan").alias("caste"), pl.col("woman_sharan").alias("woman")
    ).agg(b=pl.len())
    chance = (
        ours.join(theirs, on=["caste", "woman"])
        .select((pl.col("a") * pl.col("b")).sum() / both.height**2)
        .item()
    )
    return {
        "notice_gps": official.height,
        "notice_gps_linked": both.height,
        "reservation_agreement": round(both.select(same.mean()).item(), 4),
        "reservation_agreement_random_pairing": round(chance, 4),
        "reservation_agreement_block_pass": round(
            both.filter(pl.col("link_pass") == "block").select(same.mean()).item(), 4
        ),
        "caste_agreement": round(
            both.select((pl.col("caste") == pl.col("caste_sharan")).mean()).item(), 4
        ),
        "woman_agreement": round(
            both.select((pl.col("woman") == pl.col("woman_sharan")).mean()).item(), 4
        ),
    }


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(table, path):
    # A rebuild that changes nothing keeps the published bytes: downstream
    # studies pin these files by checksum.
    if path.exists() and pl.read_parquet(path).equals(table):
        return {"path": path.name, "rows": table.height, "sha256": sha(path)}
    temp = path.with_suffix(".tmp")
    table.write_parquet(temp, compression="zstd")
    temp.replace(path)
    return {"path": path.name, "rows": table.height, "sha256": sha(path)}


def transliterate(out=TRANSLITERATIONS):
    """Romanize every distinct Devanagari GP name the links read. Needs the
    `transliterate` dependency group (indicate and PyTorch)."""
    import indicate

    names = set(
        pl.read_parquet(INPUTS["reservations_2021"])
        .filter(pl.col("post_id") == 3)["panchayat"]
        .drop_nulls()
    )
    names |= set(pl.read_parquet(INPUTS["winners_2011"])["panchayat_raw"].drop_nulls())
    names |= set(
        pl.read_parquet(INPUTS["seats_2006"])
        .filter(pl.col("office") == "mukhiya")["gram_panchayat"]
        .drop_nulls()
    )
    # Names already romanized keep their reading, so adding a source cannot
    # move the links built on the earlier ones.
    done = transliterations(out) if out.exists() else {}
    if done and version("indicate") != generator(out)["indicate"]:
        raise SystemExit("indicate differs from the version that made the table")
    names = sorted(names - set(done))
    latin = []
    # Batches bound memory; one call on all names was killed for memory.
    for start in range(0, len(names), 200):
        batch = names[start : start + 200]
        latin += indicate.transliterate_batch(batch, source="hindi", engine=["model"])
    done.update(zip(names, latin, strict=True))
    table = pl.DataFrame(
        {"native": sorted(done), "latin": [done[n] for n in sorted(done)]}
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    info = write(table, out)
    info["generator"] = {"indicate": version("indicate"), "engine": "model"}
    (out.parent / "place_transliterations.json").write_text(
        json.dumps(info, indent=2) + "\n"
    )


def build(out=OUT):
    translit = transliterations()
    l1621, c1621 = link_2016_2021(translit)
    l1116, c1116 = link_2011_2016(translit)
    l06, c06 = link_2006_sharan(translit)
    l0616, c0616 = link_2006_2016(l1116)
    manifest = {
        "purpose": (
            "Research crosswalks between Mukhiya seats of different elections. "
            "A link asserts that names agree inside the same block, not that "
            "boundaries are unchanged."
        ),
        "matcher": {
            "preclink": version("preclink"),
            "name_threshold": NAME_THRESHOLD,
            "ward_pass_threshold": WARD_PASS_THRESHOLD,
        },
        "inputs": {
            str(p): sha(p) for p in [*INPUTS.values(), TRANSLITERATIONS, BLOCKS_2011]
        },
        "code_sha256": sha(__file__),
        "validation": {
            "mukhiya_2016_2021": c1621,
            "mukhiya_2011_2016": c1116,
            "mukhiya_2006_sharan": c06,
            "mukhiya_2006_2016": c0616,
        },
        "files": [
            write(l1621, out / "mukhiya_2016_2021.parquet"),
            write(l1116, out / "mukhiya_2011_2016.parquet"),
            write(l06, out / "mukhiya_2006_sharan.parquet"),
            write(l0616, out / "mukhiya_2006_2016.parquet"),
        ],
    }
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(manifest["validation"], indent=2))


def check(out=OUT):
    manifest = json.loads((out / "MANIFEST.json").read_text())
    for path, digest in manifest["inputs"].items():
        if sha(path) != digest:
            raise ValueError(f"Input changed since the link was built: {path}")
    for info in manifest["files"]:
        table = pl.read_parquet(out / info["path"])
        if sha(out / info["path"]) != info["sha256"] or table.height != info["rows"]:
            raise ValueError(f"{info['path']} differs from its manifest")
    l1621 = pl.read_parquet(out / "mukhiya_2016_2021.parquet")
    l1116 = pl.read_parquet(out / "mukhiya_2011_2016.parquet")
    l06 = pl.read_parquet(out / "mukhiya_2006_sharan.parquet")
    l0616 = pl.read_parquet(out / "mukhiya_2006_2016.parquet")
    for table, keys in [
        (l1621, [["district_code", "block_code", "unit_code"], ["unit_id_2021"]]),
        (l1116, [["record_id_2011"], ["district_code", "block_code", "unit_code"]]),
        (l06, [["ugp"], ["district", "block", "gram_panchayat"]]),
        (l0616, [["ugp"], ["district_code", "block_code", "unit_code"]]),
    ]:
        for key in keys:
            if table.select(key).is_duplicated().any():
                raise ValueError(f"Link is not one-to-one on {key}")
    print("Linkage files match their manifest and are one-to-one.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["transliterate", "build", "check"])
    stage = parser.parse_args().stage
    {"transliterate": transliterate, "build": build, "check": check}[stage]()


if __name__ == "__main__":
    main()

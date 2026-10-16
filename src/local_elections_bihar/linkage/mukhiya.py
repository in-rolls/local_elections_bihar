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
OUT = DATA / "linkage"
TRANSLITERATIONS = OUT / "place_transliterations.parquet"
BLOCKS_2011 = DATA / "crosswalks" / "block_2011_2016.csv"
INPUTS = {
    "seats_2016": DATA / "2016/seats.parquet",
    "seats_2021": DATA / "2021/seats.parquet",
    "reservations_2021": DATA / "2021/current_reservations.parquet",
    "winners_2011": DATA / "2011/mukhiya_reports/winner_records.parquet",
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
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
CODE_PREFIX = re.compile(r"^\s*\d+\s*-\s*")


# A name may state a direction, a twin-village qualifier, both or neither. Two
# names conflict only when both state one from the same family and they differ.
QUALIFIER_FAMILIES = (
    frozenset({"east", "west", "north", "south"}),
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
                pl.col("latin").alias("gp_2021_latin"),
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
            "gp_2021_latin",
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
                pl.col("latin").alias("gp_2011_latin"),
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
            "gp_2011_latin",
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


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(table, path):
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
    names = sorted(names)
    latin = []
    # Batches bound memory; one call on all names was killed for memory.
    for start in range(0, len(names), 200):
        batch = names[start : start + 200]
        latin += indicate.transliterate_batch(batch, source="hindi", engine=["model"])
    table = pl.DataFrame({"native": names, "latin": latin})
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
        "validation": {"mukhiya_2016_2021": c1621, "mukhiya_2011_2016": c1116},
        "files": [
            write(l1621, out / "mukhiya_2016_2021.parquet"),
            write(l1116, out / "mukhiya_2011_2016.parquet"),
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
    for table, keys in [
        (l1621, [["district_code", "block_code", "unit_code"], ["unit_id_2021"]]),
        (l1116, [["record_id_2011"], ["district_code", "block_code", "unit_code"]]),
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

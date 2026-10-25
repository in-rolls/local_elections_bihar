"""Write data/release/2006/ from the SEC's 2006 workbooks.

    python -m local_elections_bihar.parse.release_2006          # build
    python -m local_elections_bihar.parse.release_2006 --check  # verify

seats.parquet holds every seat read: ward member, panch, samiti and zila
parishad seats with their printed reservation (members_2006), and the mukhiya
and sarpanch seats from the profile workbooks (winners_2006), which state no
reservation. winner_profiles.parquet holds the mukhiya and sarpanch profiles.
data/checks/ gets each reservation and caste spelling beside its reading.
"""

import argparse
import collections
import csv
import sys

import polars as pl

from local_elections_bihar.parse import members_2006, winners_2006
from local_elections_bihar.parse.schema_2006 import TABLES
from local_elections_bihar.paths import CHECKS, RELEASE
from local_elections_bihar.shared import release

OUT = RELEASE / "2006"
CODE = [
    "parse/release_2006.py",
    "parse/schema_2006.py",
    "parse/members_2006.py",
    "parse/winners_2006.py",
    "parse/sec_workbooks.py",
    "year2011/hindi.py",
    "year2011/kruti_dev_010.json",
]


def head_seat(profile):
    return {
        "office": profile["office"],
        "district": profile["district"],
        "district_from_file": profile["district_from_file"],
        "block": profile["block"],
        "gram_panchayat": profile["gram_panchayat"],
        "constituency_no": profile["serial"],
        "constituency_name": None,
        "winner": profile["winner"],
        "winner_raw": profile["winner_raw"],
        "vacant": profile["winner"] is None,
        "reserved_raw": None,
        "reserved_caste_local": None,
        "reserved_caste": None,
        "reserved_woman_raw": None,
        "reserved_woman": None,
        "source_path": profile["source_path"],
        "source_sheet": profile["source_sheet"],
        "source_row": profile["source_row"],
    }


def vocabulary(path, rows, raw, read, by=None):
    counts = collections.Counter(
        ((r[by] if by else ""), r[raw] or "", r[read] or "") for r in rows
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow([*([by] if by else []), raw, read, "rows"])
        for (group, text, value), n in sorted(
            counts.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1])
        ):
            writer.writerow([*([group] if by else []), text, value, n])


def build():
    members = members_2006.rows()
    profiles = [
        row
        for office, folder in winners_2006.SOURCES.items()
        for row in winners_2006.rows(office, folder)
    ]
    tables = {"seats": members + [head_seat(p) for p in profiles]}
    tables["winner_profiles"] = profiles
    CHECKS.mkdir(parents=True, exist_ok=True)
    vocabulary(
        CHECKS / "reserved_2006_vocabulary.csv",
        members,
        "reserved_caste_local",
        "reserved_caste",
    )
    vocabulary(
        CHECKS / "winner_caste_2006_vocabulary.csv",
        profiles,
        "winner_caste_raw",
        "winner_caste",
        by="office",
    )
    release.write(
        OUT,
        tables,
        TABLES,
        CODE,
        year=2006,
        source="SEC Bihar 2006 workbooks under data/raw/sec_documents/",
    )
    return frame_summary()


def frame_summary():
    seats = pl.read_parquet(OUT / "seats.parquet")
    return (
        seats.group_by("office")
        .agg(
            pl.len().alias("seats"),
            pl.col("district").n_unique().alias("districts"),
            pl.col("reserved_caste").is_not_null().sum().alias("caste_read"),
            pl.col("vacant").sum().alias("vacant"),
        )
        .sort("office")
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    if parser.parse_args().check:
        release.verify(OUT, TABLES)
        return 0
    print(build())
    release.verify(OUT, TABLES)
    return 0


if __name__ == "__main__":
    sys.exit(main())

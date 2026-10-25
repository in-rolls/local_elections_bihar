"""Check that the undated mukhiya profile workbooks are the 2006 winners.

    python -m local_elections_bihar.build.profile_year_check

Mukhiya_2006/ arrived under that name and its workbooks print no year, except
Gaya's, whose title reads "पंचायत आम निर्वाचन, 2011". The 2011 winner reports
(release/2011/mukhiya_reports) state whether each 2011 winner held office in
2006. If the profiles are the 2006 winners, they should name the 2011 winner
where that winner says "मुखिया" for 2006, and almost never where the winner
says no office; if they were 2011 lists, both groups would match. Writes
data/checks/winner_profiles_2006_year.csv and fails if the gap closes.
"""

import csv
import difflib
import re
import sys

import polars as pl

from local_elections_bihar.paths import CHECKS, RELEASE

OUT = CHECKS / "winner_profiles_2006_year.csv"
HONORIFIC = re.compile(r"^(?:श्रीमती|श्रीमति|श्री|सुश्री|मो0|डा0)\s*")
SAME = 0.85


def bare(name):
    # spacing, full stops and the abbreviation zero (Latin or Devanagari)
    return re.sub(r"[\s.0\u0966]", "", HONORIFIC.sub("", (name or "").strip()))


def claim(text):
    text = text or ""
    if "मुखिया" in text:
        return "mukhiya in 2006"
    if "नह" in text:
        return "no office in 2006"
    return "not stated"


def main():
    profiles = (
        pl.read_parquet(RELEASE / "2006" / "winner_profiles.parquet")
        .filter(pl.col("office") == "mukhiya")
        .select(
            pl.col("district_from_file")
            .str.to_uppercase()
            .str.strip_chars()
            .alias("d"),
            pl.col("gram_panchayat").str.strip_chars().alias("gp"),
            pl.col("winner").alias("winner_2006"),
            pl.col("source_path"),
        )
    )
    reports = pl.read_parquet(
        RELEASE / "2011" / "mukhiya_reports" / "winner_records.parquet"
    ).select(
        pl.col("district_raw").str.to_uppercase().str.strip_chars().alias("d"),
        pl.col("panchayat_raw").str.strip_chars().alias("gp"),
        pl.col("candidate_name").alias("winner_2011"),
        pl.col("previous_office_2006_raw").alias("office_2006"),
    )
    joined = profiles.join(reports, on=["d", "gp"], how="inner").to_dicts()
    tally = {}
    for row in joined:
        same = (
            difflib.SequenceMatcher(
                None, bare(row["winner_2006"]), bare(row["winner_2011"])
            ).ratio()
            >= SAME
        )
        key = (claim(row["office_2006"]), "GAYA" if row["d"] == "GAYA" else "other")
        n, hits = tally.get(key, (0, 0))
        tally[key] = (n + 1, hits + same)
    with OUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["claim_2011", "district", "panchayats", "same_winner_share"])
        for (said, where), (n, hits) in sorted(tally.items()):
            writer.writerow([said, where, n, round(hits / n, 3)])
    share = {}
    for said in ("mukhiya in 2006", "no office in 2006"):
        n = sum(v[0] for k, v in tally.items() if k[0] == said)
        hits = sum(v[1] for k, v in tally.items() if k[0] == said)
        share[said] = hits / n
        print(f"2011 winner says {said}: {n} panchayats, {hits / n:.1%} same winner")
    if share["mukhiya in 2006"] < 0.5 or share["no office in 2006"] > 0.1:
        print("the profiles no longer read as 2006 winners")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

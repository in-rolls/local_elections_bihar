"""Audit the 2021 panchayat release against sources that share no code with it.

Schema checks (types, domains, keys) live in schemas_2021 and run during the
build. This audit compares the release with the portal's seat totals, the SEC's
2021 report, the portal's statistics API and a fresh urllib re-download, and
prints the distributions that would expose a wrong parse.
"""

import argparse
import base64
import collections
import gzip
import json
import random
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

import polars as pl
from bs4 import BeautifulSoup
from matching import name_key
from sec_portal import completed_bytes, decode_records

PORTAL = "https://sec25.bihar.gov.in"
REPORT_URL = "https://sec.bihar.gov.in/PanchayatRpt/ch{}.aspx"
AGENT = "local-elections-bihar/1.0 public research archive (audit)"
# Chapter 13 block tables in page order, and chapter 17 row labels, as SEC post IDs.
BLOCK_TABLES = {3: 1, 4: 3, 5: 5, 6: 6, 7: 2}
ELECTED_LABELS = {
    "वार्ड सदस्य": 1,
    "पंच": 2,
    "मुखिया": 3,
    "सरपंच": 4,
    "पंचायत समिति": 5,
    "जिला परिषद": 6,
}


def http(url, params=None, body=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "User-Agent": AGENT,
            "X-Requested-With": "XMLHttpRequest",
            **({"Content-Type": "application/json"} if body else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def report_tables(folder):
    tables = {}
    folder.mkdir(parents=True, exist_ok=True)
    for chapter in (13, 17):
        path = folder / f"ch{chapter}.html.gz"
        if not path.exists():
            path.write_bytes(gzip.compress(http(REPORT_URL.format(chapter))))
        soup = BeautifulSoup(gzip.decompress(path.read_bytes()), "html.parser")
        tables[chapter] = [
            [
                [" ".join(c.get_text(" ").split()) for c in tr.select("th,td")]
                for tr in t.select("tr")
            ]
            for t in soup.select("table")
        ]
    return tables


def portal_totals(archives):
    with tarfile.open(archives / "2021_offices_frame.tar") as tar:
        member = tar.getmember("2021/offices/frame/totals.jsonl.gz")
        event = completed_bytes(tar.extractfile(member).read())
    return decode_records(base64.b64decode(event["body_base64"]))


def audit(release, archives, report_dir, resample, seed):
    t = {p.stem: pl.read_parquet(p) for p in release.glob("*.parquet")}
    seats, cands, rows, winners = (
        t["seats"],
        t["candidates"],
        t["result_rows"],
        t["winners"],
    )
    report, flags = {}, []

    # 1. Seat frame against the portal's own totals, per district and office.
    totals = portal_totals(archives)
    expected = pl.DataFrame(
        [
            {
                "district_id": int(r["districtID"]),
                "post_id": p,
                "portal": int(r[f"p{p}"]),
            }
            for r in totals
            for p in range(1, 7)
        ],
        schema={"district_id": pl.Int32, "post_id": pl.Int8, "portal": pl.Int64},
    )
    found = seats.group_by("district_id", "post_id").len("release")
    diff = expected.join(
        found, on=["district_id", "post_id"], how="full", coalesce=True
    )
    diff = diff.filter(pl.col("portal") != pl.col("release").fill_null(0))
    report["seats_vs_portal_totals"] = {
        "seats": dict(seats.group_by("post_id").len().sort("post_id").iter_rows()),
        "district_office_mismatches": diff.to_dicts(),
    }
    if diff.height:
        flags.append("seats_vs_portal_totals")
    report["seat_status"] = {
        str(k): dict(v.group_by("status").len().iter_rows())
        for (k,), v in seats.group_by("post_id")
    }

    # 2. Winners: the flagged winner should have the highest summed vote.
    totals_by = rows.group_by("post_id", "unit_id", "result_serial").agg(
        pl.col("votes").sum(), pl.col("elected").any()
    )
    top = totals_by.group_by("post_id", "unit_id").agg(
        pl.col("votes").max().alias("top")
    )
    flagged = totals_by.filter("elected").join(top, on=["post_id", "unit_id"])
    not_top = flagged.filter(pl.col("votes") < pl.col("top"))
    report["winners"] = {
        "by_post_and_basis": winners.group_by("post_id", "winner_basis")
        .len()
        .sort("post_id", "winner_basis")
        .to_dicts(),
        "winner_not_in_candidate_list": winners.filter(
            pl.col("candidate_serial").is_null()
        ).height,
        "flagged_winner_below_top_vote": not_top.height,
        "examples_below_top": not_top.head(5).to_dicts(),
        "partial_winner_flags": seats.filter("winner_flag_partial").height,
    }

    # 3. SEC 2021 report: candidates by office and gender, and by block.
    tables = report_tables(report_dir)
    ours = cands.group_by("post_id", "candidate_gender").len()
    by_office = {}
    for row in tables[13][2]:
        if len(row) == 5 and row[0].rstrip("-").isdigit():
            post = int(row[0].rstrip("-"))
            mine = dict(
                ours.filter(pl.col("post_id") == post)
                .select("candidate_gender", "len")
                .iter_rows()
            )
            by_office[post] = {
                "report": {
                    "male": int(row[2]),
                    "female": int(row[3]),
                    "total": int(row[4]),
                },
                "release": {
                    "male": mine.get("male", 0),
                    "female": mine.get("female", 0),
                    "other": mine.get("other", 0),
                    "unlisted_gender_unknown": mine.get(None, 0),
                    "total": sum(mine.values()),
                },
            }
    report["sec_report_candidates_by_office"] = by_office
    block_names = seats.select("post_id", "unit_id", "district", "block")
    ours_block = collections.Counter(
        (p, name_key(d), name_key(b))
        for p, d, b in cands.join(block_names, on=["post_id", "unit_id"])
        .filter(pl.col("block").is_not_null())
        .select("post_id", "district", "block")
        .iter_rows()
    )
    theirs = collections.Counter()
    for index, post in BLOCK_TABLES.items():
        if post == 6:
            continue
        for row in tables[13][index]:
            if len(row) == 6 and row[0].isdigit():
                theirs[(post, name_key(row[1]), name_key(row[2]))] += int(row[5])
    matched = set(ours_block) & set(theirs)
    differences = sorted(
        ((k, theirs[k], ours_block[k]) for k in matched if theirs[k] != ours_block[k]),
        key=lambda x: -abs(x[1] - x[2]),
    )
    report["sec_report_candidates_by_block"] = {
        "report_blocks": len(theirs),
        "name_matched": len(matched),
        "equal": len(matched) - len(differences),
        "absolute_difference_total": sum(abs(a - b) for _, a, b in differences),
        "largest_differences": [
            {"post": k[0], "district": k[1], "block": k[2], "report": a, "release": b}
            for k, a, b in differences[:10]
        ],
        "unmatched_report_blocks": len(set(theirs) - matched),
    }
    elected = {}
    for row in tables[17][2]:
        post = ELECTED_LABELS.get(row[0])
        if post and len(row) == 11:
            w = winners.filter(pl.col("post_id") == post)
            elected[post] = {
                "report": {"female": int(row[9]), "total": int(row[10])},
                "release": {
                    "total": w.height,
                    "female": w.filter(pl.col("candidate_gender") == "female").height,
                    "gender_unknown": w.filter(
                        pl.col("candidate_gender").is_null()
                    ).height,
                    "sole_candidate": w.filter(
                        pl.col("winner_basis") == "sole_candidate"
                    ).height,
                },
            }
    report["sec_report_elected_by_office"] = elected

    # 4. Current feeds: coverage, and agreement with the dated 2021 winner.
    current = t["current_winners"]
    joined = winners.join(
        current.select("post_id", "unit_id", "candidate_name", "vacant_placeholder"),
        on=["post_id", "unit_id"],
        how="left",
        suffix="_current",
    )
    agreement = collections.Counter()
    for post, dated, now, vacant in joined.select(
        "post_id", "winner_name", "candidate_name", "vacant_placeholder"
    ).iter_rows():
        if vacant:
            status = "vacant_now"
        elif now is None:
            status = "no_current_row"
        elif name_key(dated) == name_key(now):
            status = "same_name"
        else:
            status = "different_name"
        agreement[(post, status)] += 1
    report["dated_vs_current_winner"] = {
        f"p{p}_{s}": n for (p, s), n in sorted(agreement.items())
    }
    report["current_feeds"] = {
        name: {
            "rows": t[name].height,
            "unmatched_to_seats": t[name].filter(pl.col("unit_id").is_null()).height,
            "repeated_seats": t[name]
            .filter(pl.col("unit_id").is_not_null())
            .group_by("post_id", "unit_id")
            .len()
            .filter(pl.col("len") > 1)
            .height,
        }
        for name in ("current_winners", "current_reservations")
    }
    report["current_feeds"]["vacant_placeholders"] = current.filter(
        "vacant_placeholder"
    ).height
    for name, v in report["current_feeds"].items():
        if isinstance(v, dict) and (v["unmatched_to_seats"] or v["repeated_seats"]):
            flags.append(f"{name}_coverage")

    # 5. Portal statistics API: statewide winner gender shares by office.
    stats = {}
    labels = {"पुरुष": "c01", "महिला": "c02", "अन्य": "c03"}
    for post in range(1, 7):
        state = json.loads(
            http(
                f"{PORTAL}/api/MapApi/GetWinnersReservationCategoryWise",
                body={"reservationType": "Gender", "post": str(post), "district": "33"},
            )
        )[0]
        # The portal counts vacant placeholders in the denominator but in no gender.
        feed = current.filter(pl.col("post_id") == post)
        counts = collections.Counter(
            labels.get((g or "").strip()) for g in feed["candidate_gender_raw"]
        )
        mine = {
            c: round(100 * counts[c] / feed.height, 2) for c in ("c01", "c02", "c03")
        }
        stats[post] = {"portal": {c: state[c] for c in mine}, "release": mine}
        if any(abs(mine[c] - state[c]) > 0.1 for c in mine):
            flags.append(f"gender_share_p{post}")
    report["portal_gender_statistics"] = stats

    # 6. Fresh urllib re-download of a random sample of seats.
    rng = random.Random(seed)
    sample = rng.sample(
        seats.filter(pl.col("status") == "results").to_dicts(), resample
    )
    changed = []
    for s in sample:
        params = {
            "postId": s["post_id"],
            "districtId": s["district_id"],
            "blockId": "" if s["block_id"] is None else s["block_id"],
            "panchayatId": "" if s["panchayat_id"] is None else s["panchayat_id"],
            "ward": s["seat_no"] if s["post_id"] in (1, 2) else "",
            "psn": s["seat_no"] if s["post_id"] == 5 else -1,
            "jpn": s["seat_no"] if s["post_id"] == 6 else -1,
            "phase": "2021_1",
        }
        fresh = decode_records(
            http(
                f"{PORTAL}/sec_new/Panchayat/Result", {"handler": "GetResult", **params}
            )
        )
        saved = rows.filter(
            (pl.col("post_id") == s["post_id"]) & (pl.col("unit_id") == s["unit_id"])
        ).sort("source_row")
        got = [(r["OrderBy"], r["TotalVote"], r["IsWin"]) for r in fresh]
        have = list(saved.select("result_serial", "votes", "elected").iter_rows())
        if got != have:
            changed.append({"post": s["post_id"], "unit": s["unit_id"]})
    report["resample"] = {"seats": len(sample), "changed": changed}
    if changed:
        flags.append("resample_changed")

    # 7. By-elections: listed totals, and winners against summed votes.
    bye_seats, bye_rows = t["byelection_seats"], t["byelection_result_rows"]
    bye_totals = bye_rows.group_by("phase", "post_id", "unit_id", "result_serial").agg(
        pl.col("votes").sum(), pl.col("elected").any()
    )
    bye_top = bye_totals.group_by("phase", "post_id", "unit_id").agg(
        pl.col("votes").max().alias("top")
    )
    bye_low = (
        bye_totals.filter("elected")
        .join(bye_top, on=["phase", "post_id", "unit_id"])
        .filter(pl.col("votes") < pl.col("top"))
    )
    report["byelections"] = {
        "seats": bye_seats.group_by("phase", "post_id")
        .len()
        .sort("phase", "post_id")
        .to_dicts(),
        "status": dict(bye_seats.group_by("status").len().iter_rows()),
        "winners_by_basis": dict(
            t["byelection_winners"].group_by("winner_basis").len().iter_rows()
        ),
        "flagged_winner_below_top_vote": bye_low.height,
    }
    if bye_low.height:
        flags.append("byelection_winner_below_top_vote")

    # 8. Distributions that would expose a wrong parse.
    report["distributions"] = {
        "candidates_by_post": dict(
            cands.group_by("post_id").len().sort("post_id").iter_rows()
        ),
        "result_only_candidates": dict(
            cands.filter(~pl.col("in_candidate_list"))
            .group_by("post_id")
            .len()
            .iter_rows()
        ),
        "implausible_ages": cands.filter("candidate_age_implausible").height,
        "age_quantiles": cands.select(
            pl.col("candidate_age").quantile(q).alias(str(q))
            for q in (0, 0.01, 0.5, 0.99, 1)
        ).to_dicts()[0],
        "result_votes_max": rows["votes"].max(),
        "result_votes_null": rows["votes"].null_count(),
        "match_methods": dict(rows.group_by("match_method").len().iter_rows()),
        "candidates_per_seat": dict(
            seats.group_by("candidate_records")
            .len()
            .sort("candidate_records")
            .iter_rows()
        ),
    }
    report["flags"] = flags
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release", type=Path, default=Path("data/release/2021_panchayat")
    )
    parser.add_argument(
        "--archives", type=Path, default=Path("data/interim/2021/archive")
    )
    parser.add_argument("--report", type=Path, default=Path("data/raw/report_2021"))
    parser.add_argument("--resample", type=int, default=200)
    parser.add_argument("--seed", type=int, default=2021)
    args = parser.parse_args()
    report = audit(args.release, args.archives, args.report, args.resample, args.seed)
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    (args.release / "audit.json").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()

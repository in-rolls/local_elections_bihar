"""Audit the parsed 2021 office tables for completeness and internal consistency.

Checks marked "independent" re-read the SEC service with urllib rather than the
collector's session code, so a defect in the collector cannot also pass them.
"""

import argparse
import base64
import collections
import gzip
import json
import random
import re
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import pyarrow.parquet as pq
from bs4 import BeautifulSoup
from matching import name_key
from offices_2021 import POSTS, ROOT, WARD_POSTS, request_params
from sec_portal import completed, decode_records

STATS_URL = "https://sec25.bihar.gov.in/api/MapApi/GetWinnersReservationCategoryWise"
RESULT_URL = "https://sec25.bihar.gov.in/sec_new/Panchayat/Result"
CANDIDATE_URL = "https://sec25.bihar.gov.in/sec_new/Panchayat/ContestingCandidates"
AGENT = "local-elections-bihar/1.0 public research archive (audit)"
WINNER_SUFFIX = re.compile(r"\s*\(विजेता\)\s*$")


def norm(name):
    name = WINNER_SUFFIX.sub("", unicodedata.normalize("NFC", name or ""))
    return " ".join(name.split())


def table(path):
    return pq.read_table(path).to_pylist()


def examples(items, n=5):
    return sorted(items)[:n]


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


REPORT_URL = "https://sec.bihar.gov.in/PanchayatRpt/ch{}.aspx"
# Report row labels for SEC post IDs; chapter 13 lists offices in post-ID order.
ELECTED_LABELS = {
    "वार्ड सदस्य": 1,
    "पंच": 2,
    "मुखिया": 3,
    "सरपंच": 4,
    "पंचायत समिति": 5,
    "जिला परिषद": 6,
}
BLOCK_TABLES = {3: 1, 4: 3, 5: 5, 6: 6, 7: 2}
GENDER = {"पुरुष": "male", "महिला": "female"}


def report_tables(folder):
    """Chapters 13 and 17 of the SEC 2021 report, saved once as gzipped HTML."""

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


def compare_report(tables, frame, candidates, seats, coverage, names, failures):
    ours = collections.Counter(
        (c["post_id"], GENDER.get((c["candidate_gender"] or "").strip(), "other"))
        for c in candidates
    )
    state = {}
    for row in tables[13][2]:
        if len(row) == 5 and row[0].rstrip("-").isdigit():
            post = int(row[0].rstrip("-"))
            if post == 3:
                continue
            state[f"p{post}"] = {
                "report": {
                    "male": int(row[2]),
                    "female": int(row[3]),
                    "total": int(row[4]),
                },
                "portal": {
                    "male": ours[(post, "male")],
                    "female": ours[(post, "female")],
                    "other": ours[(post, "other")],
                    "total": sum(n for (p, _), n in ours.items() if p == post),
                },
            }
    unit_names = {
        (u["post_id"], u["unit_id"]): (u["district"], u["block"]) for u in frame
    }
    blocks = collections.Counter(
        (c["post_id"], *map(norm, unit_names[(c["post_id"], c["unit_id"])]))
        for c in candidates
        if c["post_id"] != 6
    )
    block_rows = collections.Counter()
    for index, post in BLOCK_TABLES.items():
        if post in (3, 6):
            continue
        for row in tables[13][index]:
            if len(row) == 6 and row[0].isdigit():
                block_rows[(post, norm(row[1]), norm(row[2]))] += int(row[5])
    matched = set(blocks) & set(block_rows)
    block_check = {
        "report_blocks": len(block_rows),
        "portal_blocks": len(blocks),
        "name_matched": len(matched),
        "matched_equal_counts": sum(blocks[k] == block_rows[k] for k in matched),
        "matched_count_differences": examples(
            (k, block_rows[k], blocks[k]) for k in matched if blocks[k] != block_rows[k]
        ),
        "unmatched_report_blocks": examples(set(block_rows) - matched),
    }
    unopposed = {
        (c["post_id"], c["unit_id"])
        for c in coverage
        if c["result_records"] == 0 and c["candidate_records"] == 1
    }
    gender = {
        (c["post_id"], c["unit_id"], c["candidate_serial"]): GENDER.get(
            (c["candidate_gender"] or "").strip(), "other"
        )
        for c in candidates
    }
    elected = collections.Counter()
    for (post, unit), (won, _) in seats.items():
        if len(won) == 1:
            elected[(post, "total")] += 1
            elected[(post, gender.get((post, unit, won[0]), "not_in_list"))] += 1
    serial = {(c["post_id"], c["unit_id"]): c["candidate_serial"] for c in candidates}
    for post, unit in unopposed:
        elected[(post, "total")] += 1
        elected[(post, "unopposed")] += 1
        elected[(post, gender.get((post, unit, serial[(post, unit)])))] += 1
    elected_check = {}
    for row in tables[17][2]:
        post = ELECTED_LABELS.get(row[0])
        if post and post != 3 and len(row) == 11:
            elected_check[f"p{post}"] = {
                "report": {"female": int(row[9]), "total": int(row[10])},
                "portal_flagged_or_unopposed": {
                    k: elected[(post, k)]
                    for k in ("female", "male", "other", "unopposed", "total")
                },
            }
    for post, v in state.items():
        if v["portal"]["total"] and v["portal"]["total"] != v["report"]["total"]:
            failures.append(f"report_candidates_{post}")
    return {
        "candidates_by_office": state,
        "candidates_by_block": block_check,
        "elected_by_office": elected_check,
    }


def audit(raw, parsed, resample, seed):
    frame = table(raw / f"{ROOT}/frame.parquet")
    coverage = table(parsed / "coverage.parquet")
    candidates = table(parsed / "candidates.parquet")
    results = table(parsed / "result_rows.parquet")
    winners = table(parsed / "current_winners.parquet")
    reservations = table(parsed / "current_reservations.parquet")
    report, failures = {}, []

    # 1. Frame against the portal's published seat totals (saved response).
    totals = decode_records(
        base64.b64decode(
            completed(raw / f"{ROOT}/frame/totals.jsonl.gz")["body_base64"]
        )
    )
    seats = collections.Counter((u["district_id"], u["post_id"]) for u in frame)
    gaps = [
        (int(t["districtID"]), p, int(t[f"p{p}"]), seats[(int(t["districtID"]), p)])
        for t in totals
        for p in POSTS
        if int(t[f"p{p}"]) != seats[(int(t["districtID"]), p)]
    ]
    report["frame_vs_portal_totals"] = {
        "seats": {p: sum(n for (_, q), n in seats.items() if q == p) for p in POSTS},
        "mismatches": gaps,
    }
    if gaps:
        failures.append("frame_vs_portal_totals")

    # 2. Completeness: every seat has a completed candidate and result request, and
    # every seat without results carries phase evidence.
    by_post = collections.defaultdict(collections.Counter)
    missing = []
    for c in coverage:
        post = c["post_id"]
        if not (c["candidates_fetched"] and c["results_fetched"]):
            if c["phase_2021_listed"] is False:
                by_post[post]["no_2021_phase"] += 1
            else:
                missing.append(c["unit_id"] + f"_p{post}")
            continue
        if c["result_records"]:
            status = "results"
        elif c["candidate_records"] == 1:
            status = "one_candidate_no_results"
        elif c["candidate_records"] == 0:
            status = "no_candidates_no_results"
        else:
            status = "several_candidates_no_results"
        if not c["result_records"] and not c["phases_fetched"]:
            missing.append(c["unit_id"] + f"_p{post}_phase")
        by_post[post][status] += 1
    report["seat_status"] = {p: dict(v) for p, v in sorted(by_post.items())}
    report["incomplete_units"] = {"count": len(missing), "examples": examples(missing)}
    if len(coverage) != len(frame):
        failures.append("coverage_rows_differ_from_frame")
    if missing:
        failures.append("incomplete_units")

    # 3. Keys: unique candidate serials; results must name listed candidates; seats
    # split by panchayat must list the same candidates in every panchayat.
    listed = collections.defaultdict(set)
    repeated = []
    for c in candidates:
        k = (c["post_id"], c["unit_id"])
        if c["candidate_serial"] in listed[k]:
            repeated.append(k)
        listed[k].add(c["candidate_serial"])
    names = {
        (c["post_id"], c["unit_id"], c["candidate_serial"]): norm(c["candidate_name"])
        for c in candidates
    }
    rows = collections.defaultdict(list)
    for r in results:
        rows[(r["post_id"], r["unit_id"])].append(r)
    unlisted, uneven, duplicate_rows, flag_conflicts = [], [], [], []
    multiple_winners, not_top, name_diffs, totals_by_seat = [], [], [], {}
    methods = collections.Counter(r["match_method"] for r in results)
    for k, group in rows.items():
        if any(r["candidate_serial"] is None for r in group):
            unlisted.append(k)
        split = collections.defaultdict(list)
        for r in group:
            split[r["result_panchayat_id"]].append(r["result_serial"])
        if any(len(v) != len(set(v)) for v in split.values()):
            duplicate_rows.append(k)
        if len({frozenset(v) for v in split.values()}) > 1:
            uneven.append(k)
        flags = collections.defaultdict(set)
        votes = collections.Counter()
        for r in group:
            flags[r["result_serial"]].add(r["elected"])
            votes[r["result_serial"]] += r["votes"] or 0
            if r["match_method"] in ("serial_only", "name_contained"):
                name_diffs.append((*k, r["result_serial"], r["match_method"]))
        matched = {r["result_serial"]: r["candidate_serial"] for r in group}
        if any(len(f) > 1 for f in flags.values()):
            flag_conflicts.append(k)
        won = [s for s, f in flags.items() if True in f]
        if len(won) > 1:
            multiple_winners.append(k)
        if len(won) == 1 and votes[won[0]] < max(votes.values()):
            not_top.append(k)
        # Winners are carried as candidate-list serials (None if unlisted).
        totals_by_seat[k] = ([matched[s] for s in won], votes)
    report["keys"] = {
        "repeated_candidate_serials": len(repeated),
        "seats_with_results_not_in_candidate_list": len(unlisted),
        "result_match_methods": dict(methods),
        "repeated_result_rows_within_panchayat": len(duplicate_rows),
        "panchayat_splits_with_different_candidates": len(uneven),
        "result_matched_by_containment_or_serial_only": len(name_diffs),
        "examples": {
            "unlisted": examples(unlisted),
            "uneven": examples(uneven),
            "name_diffs": examples(name_diffs),
        },
    }
    for name, items in [
        ("repeated_candidate_serials", repeated),
        ("repeated_result_rows_within_panchayat", duplicate_rows),
    ]:
        if items:
            failures.append(name)

    # 4. Winners.
    seats_with_results = collections.Counter(k[0] for k in rows)
    one_winner = collections.Counter(
        k[0] for k, (won, _) in totals_by_seat.items() if len(won) == 1
    )
    no_winner = [k for k, (won, _) in totals_by_seat.items() if not won]
    report["winners"] = {
        "seats_with_results": dict(seats_with_results),
        "seats_with_one_flagged_winner": dict(one_winner),
        "seats_with_results_but_no_flag": {
            "count": len(no_winner),
            "examples": examples(no_winner),
        },
        "seats_with_several_flagged_winners": len(multiple_winners),
        "flag_differs_across_panchayat_rows": len(flag_conflicts),
        "flagged_winner_not_top_vote_total": {
            "count": len(not_top),
            "examples": examples(not_top),
        },
    }
    if multiple_winners or flag_conflicts:
        failures.append("winner_flags")

    # 5. Current feeds against the frame: one reservation per seat, winners unique.
    def seat_key(r):
        post = r["post_id"]
        if post in WARD_POSTS:
            return (post, r["district_id"], r["panchayat_id"], r["seat_no"])
        if post == 4:
            return (post, r["district_id"], r["panchayat_id"])
        if post == 5:
            return (post, r["district_id"], r["block_id"], r["seat_no"])
        return (post, r["district_id"], r["seat_no"])

    frame_keys = {seat_key(u) for u in frame}
    current = {}
    for kind, feed in [("winners", winners), ("reservations", reservations)]:
        keys = collections.Counter(seat_key(r) for r in feed)
        current[kind] = keys
        report[f"current_{kind}"] = {
            "rows": len(feed),
            "by_post": dict(collections.Counter(r["post_id"] for r in feed)),
            "repeated_seat_keys": sum(n > 1 for n in keys.values()),
            "seats_not_in_frame": len(set(keys) - frame_keys),
            "frame_seats_absent": dict(
                collections.Counter(k[0] for k in frame_keys - set(keys))
            ),
            "examples_not_in_frame": examples(map(str, set(keys) - frame_keys)),
        }
    if set(current["reservations"]) != frame_keys:
        failures.append("reservation_feed_differs_from_frame")

    # 6. Dated 2021 winners against the current winner feed, by seat and name.
    unit_key = {(u["post_id"], u["unit_id"]): seat_key(u) for u in frame}
    current_names = collections.defaultdict(set)
    for r in winners:
        current_names[seat_key(r)].add(name_key(r["candidate_name"]))
    keyed = {k: name_key(n) for k, n in names.items()}
    agree = collections.Counter()
    for k, (won, _) in totals_by_seat.items():
        if len(won) != 1:
            continue
        seat = unit_key[k]
        if seat not in current_names:
            agree[(k[0], "no_current_winner")] += 1
        elif won[0] is None:
            agree[(k[0], "winner_not_in_candidate_list")] += 1
        elif keyed.get((*k, won[0])) in current_names[seat]:
            agree[(k[0], "same_name")] += 1
        else:
            agree[(k[0], "different_name")] += 1
    report["dated_vs_current_winner"] = {f"p{p}_{s}": n for (p, s), n in agree.items()}

    # 7. Independent: portal statistics of winners' gender against the winner feed.
    labels = {"पुरुष": "c01", "महिला": "c02", "अन्य": "c03"}
    stats = {}
    for post in POSTS:
        state = json.loads(
            http(
                STATS_URL,
                body={"reservationType": "Gender", "post": str(post), "district": "33"},
            )
        )[0]
        feed = [r for r in winners if r["post_id"] == post]
        counts = collections.Counter(
            labels.get((r["candidate_gender"] or "").strip()) for r in feed
        )
        ours = {
            c: round(100 * counts[c] / len(feed), 2) if feed else None
            for c in ("c01", "c02", "c03")
        }
        stats[f"p{post}"] = {
            "portal": {c: state[c] for c in ("c01", "c02", "c03")},
            "winner_feed": ours,
            "unmapped_gender": counts[None],
        }
        if feed and any(abs(ours[c] - state[c]) > 0.05 for c in ours):
            failures.append(f"gender_share_p{post}")
    report["portal_gender_statistics"] = stats

    # 8. Independent: re-request a random sample of seats and compare with saved.
    rng = random.Random(seed)
    sample = rng.sample(frame, min(resample, len(frame)))
    changed = []
    for u in sample:
        params = {**request_params(u), "phase": "2021_1"}
        for kind, url, handler in [
            ("candidates", CANDIDATE_URL, "GetContestingCandidates"),
            ("results", RESULT_URL, "GetResult"),
        ]:
            saved = completed(
                raw / f"{ROOT}/p{u['post_id']}/{kind}/{u['unit_id']}.jsonl.gz"
            )
            if saved is None:
                continue
            fresh = decode_records(http(url, {"handler": handler, **params}))
            old = decode_records(base64.b64decode(saved["body_base64"]))
            if fresh != old:
                changed.append((u["post_id"], u["unit_id"], kind))
    report["resample"] = {"seats": len(sample), "changed": changed}
    if changed:
        failures.append("resample_changed")

    # 9. Independent: the SEC's own 2021 election report (chapters 13 and 17).
    report["sec_report_2021"] = compare_report(
        report_tables(raw.parent / "report_2021"),
        frame,
        candidates,
        totals_by_seat,
        coverage,
        names,
        failures,
    )

    # 10. Distributions that would expose a wrong parse.
    ages = [c["candidate_age"] for c in candidates if c["candidate_age"] is not None]
    votes = [r["votes"] for r in results if r["votes"] is not None]
    per_seat = collections.Counter(len(v) for v in listed.values())
    report["distributions"] = {
        "candidates_by_post": dict(
            collections.Counter(c["post_id"] for c in candidates)
        ),
        "age_missing": len(candidates) - len(ages),
        "age_min_max": [min(ages, default=None), max(ages, default=None)],
        "ages_below_21_or_above_100": sum(a < 21 or a > 100 for a in ages),
        "gender_values": dict(
            collections.Counter(c["candidate_gender"] for c in candidates)
        ),
        "votes_missing": len(results) - len(votes),
        "votes_min_max": [min(votes, default=None), max(votes, default=None)],
        "candidates_per_seat": dict(sorted(per_seat.items())),
        "phone_numbers_in_raw_cell": sum(
            "MobileNo" in r["raw_cell"] for r in [*candidates, *results, *winners]
        ),
    }
    report["failures"] = failures
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/statewide_2021"))
    parser.add_argument(
        "--parsed", type=Path, default=Path("data/interim/2021/offices")
    )
    parser.add_argument("--resample", type=int, default=200)
    parser.add_argument("--seed", type=int, default=2021)
    args = parser.parse_args()
    report = audit(args.raw, args.parsed, args.resample, args.seed)
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    (args.parsed / "audit.json").write_text(text + "\n")
    print(text)
    raise SystemExit(1 if report["failures"] else 0)


if __name__ == "__main__":
    main()

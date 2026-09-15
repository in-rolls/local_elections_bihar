"""Collect 2021 records for the five non-mukhiya offices; build_2021.py parses them.

Offices (SEC post IDs): 1 ward member, 2 panch, 4 sarpanch, 5 panchayat samiti
member, 6 zila parishad member. Mukhiya (3) remains in sec_2021.py.
"""

import argparse
import collections
import concurrent.futures
import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from sec_portal import decode_records, fetch

POSTS = (1, 2, 4, 5, 6)
WARD_POSTS = (1, 2)
PHASE = "2021_1"
TOTALS_URL = "https://sec25.bihar.gov.in/api/MapApi/districts"
ROOT = "2021/offices"


def unit_id(u):
    d, b, p, s = u["district_id"], u["block_id"], u["panchayat_id"], u["seat_no"]
    if u["post_id"] in WARD_POSTS:
        return f"d{d}_b{b}_p{p}_w{s}"
    if u["post_id"] in (3, 4):
        return f"d{d}_b{b}_p{p}"
    if u["post_id"] == 5:
        return f"d{d}_b{b}_s{s}"
    return f"d{d}_z{s}"


def build_frame(raw, workers):
    """Enumerate every 2021 seat and require the portal's own seat totals."""
    panchayats = pq.read_table(raw / "2021/frame.parquet").to_pylist()
    blocks = sorted({(u["district_id"], u["block_id"]) for u in panchayats})
    districts = sorted({u["district_id"] for u in panchayats})
    names = {
        "district": {u["district_id"]: u["district"] for u in panchayats},
        "block": {(u["district_id"], u["block_id"]): u["block"] for u in panchayats},
    }

    def wards(u):
        d, b, p = u["district_id"], u["block_id"], int(u["panchayat_id"])
        body = fetch(
            raw,
            f"{ROOT}/frame/wards/d{d}_b{b}_p{p}",
            "Result",
            {"handler": "GetWards", "districtId": d, "blockId": b, "panchayatId": p},
        )
        numbers = [int(w["w"]) for w in decode_records(body)]
        if len(numbers) != len(set(numbers)):
            raise ValueError(f"Repeated ward number: {d} {b} {p}")
        return [(u, w) for w in numbers]

    def samiti(block):
        d, b = block
        body = fetch(
            raw,
            f"{ROOT}/frame/samiti/d{d}_b{b}",
            "Result",
            {"handler": "GetPanchayatSamitiNo", "districtId": d, "blockId": b},
        )
        return [(block, int(s["i"])) for s in decode_records(body)]

    def zila(d):
        body = fetch(
            raw,
            f"{ROOT}/frame/zila/d{d}",
            "Result",
            {"handler": "GetJilaParishadNo", "districtId": d},
        )
        return [(d, int(s["i"])) for s in decode_records(body)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        ward_units = [x for g in pool.map(wards, panchayats) for x in g]
        samiti_units = [x for g in pool.map(samiti, blocks) for x in g]
        zila_units = [x for g in pool.map(zila, districts) for x in g]

    def row(post, d, b=None, p=None, s=None, panchayat=None):
        u = {
            "post_id": post,
            "district_id": d,
            "block_id": b,
            "panchayat_id": p,
            "seat_no": s,
            "district": names["district"][d],
            "block": names["block"].get((d, b)),
            "panchayat": panchayat,
        }
        return {**u, "unit_id": unit_id(u)}

    rows = [
        row(
            post,
            u["district_id"],
            u["block_id"],
            int(u["panchayat_id"]),
            w,
            u["panchayat"],
        )
        for post in WARD_POSTS
        for u, w in ward_units
    ]
    rows += [
        row(
            4,
            u["district_id"],
            u["block_id"],
            int(u["panchayat_id"]),
            panchayat=u["panchayat"],
        )
        for u in panchayats
    ]
    rows += [row(5, d, b, s=s) for (d, b), s in samiti_units]
    rows += [row(6, d, s=s) for d, s in zila_units]
    keys = [(r["post_id"], r["unit_id"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Repeated seat unit in frame")

    totals = decode_records(fetch(raw, f"{ROOT}/frame/totals", TOTALS_URL))
    expected = {
        (int(t["districtID"]), post): int(t[f"p{post}"])
        for t in totals
        for post in POSTS
    }
    found = collections.Counter((r["district_id"], r["post_id"]) for r in rows)
    gaps = {
        f"d{d}_p{post}": {"portal": n, "frame": found[(d, post)]}
        for (d, post), n in sorted(expected.items())
        if found[(d, post)] != n
    }
    extra = set(found) - set(expected)
    summary = {
        "seats": {p: sum(n for (_, q), n in found.items() if q == p) for p in POSTS},
        "portal_seats": {
            p: sum(n for (_, q), n in expected.items() if q == p) for p in POSTS
        },
        "district_post_mismatches": gaps,
        "unexpected_district_posts": sorted(map(str, extra)),
    }
    print(json.dumps(summary), flush=True)
    if gaps or extra:
        raise ValueError("Seat frame differs from portal totals")
    pq.write_table(
        pa.Table.from_pylist(rows), raw / f"{ROOT}/frame.parquet", compression="zstd"
    )


def request_params(u):
    return {
        "postId": u["post_id"],
        "districtId": u["district_id"],
        "blockId": "" if u["block_id"] is None else u["block_id"],
        "panchayatId": "" if u["panchayat_id"] is None else u["panchayat_id"],
        "ward": u["seat_no"] if u["post_id"] in WARD_POSTS else "",
        "psn": u["seat_no"] if u["post_id"] == 5 else -1,
        "jpn": u["seat_no"] if u["post_id"] == 6 else -1,
    }


def fetch_dated(raw, u):
    """Candidate list and results for one seat, with phase evidence for empties."""
    post, uid = u["post_id"], u["unit_id"]
    params = request_params(u)

    def phases():
        body = fetch(
            raw,
            f"{ROOT}/p{post}/phases/{uid}",
            "Result",
            {"handler": "GetPhases", **params},
        )
        return any(x["i"] == PHASE and x["n"] == "2021" for x in decode_records(body))

    # Ward seats are 93% of requests; their phase list is only needed to explain
    # an empty result, so it is requested after the fact rather than for every seat.
    if post not in WARD_POSTS and not phases():
        return {"post": post, "unit": uid, "reason": "2021 phase absent"}
    counts = {}
    for kind, page, handler in [
        ("candidates", "ContestingCandidates", "GetContestingCandidates"),
        ("results", "Result", "GetResult"),
    ]:
        body = fetch(
            raw,
            f"{ROOT}/p{post}/{kind}/{uid}",
            page,
            {"handler": handler, **params, "phase": PHASE},
        )
        counts[kind] = len(decode_records(body))
    if post in WARD_POSTS and not counts["results"]:
        counts["phase_2021"] = phases()
    return {"post": post, "unit": uid, **counts}


def fetch_current(raw, post, d, b, p=None):
    counts = {}
    for kind, page, handler in [
        ("winners", "WinningCandidates", "GetWinners"),
        ("reservations", "Reservation", "GetReservations"),
    ]:
        suffix = f"d{d}_b{b}" if p is None else f"d{d}_b{b}_p{p}"
        body = fetch(
            raw,
            f"current/{kind}/p{post}/{suffix}",
            page,
            {
                "handler": handler,
                "PostID": post,
                "DistrictID": d,
                "BlockID": b,
                "PanchayatID": -1 if p is None else p,
            },
        )
        counts[kind] = len(decode_records(body))
    return {"post": post, "unit": suffix, **counts}


def order(units):
    """Stable pseudo-random order so an interrupted crawl is a statewide sample."""
    return sorted(units, key=lambda u: hashlib.sha256(repr(u).encode()).digest())


def collect(raw, stage, posts, districts, workers):
    frame = [
        u
        for u in pq.read_table(raw / f"{ROOT}/frame.parquet").to_pylist()
        if u["district_id"] in districts
    ]
    if stage == "current":
        panchayats = sorted(
            {
                (u["district_id"], u["block_id"], u["panchayat_id"])
                for u in frame
                if u["post_id"] == 4
            }
        )
        blocks = sorted({(d, b) for d, b, _ in panchayats})
        jobs = [(p, d, b, g) for p in WARD_POSTS for d, b, g in panchayats]
        jobs += [(p, d, b, None) for p in (4, 5, 6) for d, b in blocks]
        jobs = [(fetch_current, (raw, *j)) for j in order(jobs) if j[0] in posts]
    else:
        units = order(u for u in frame if u["post_id"] in posts)
        jobs = [(fetch_dated, (raw, u)) for u in units]
    failed = 0

    def run(job):
        function, args = job
        try:
            return function(*args)
        except Exception as error:
            # The ledger keeps the failed attempt; the next pass retries it.
            unit = args[1]["unit_id"] if isinstance(args[1], dict) else args[1:]
            return {"unit": str(unit), "error": f"{type(error).__name__}: {error}"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for done, result in enumerate(pool.map(run, jobs), 1):
            failed += "error" in result
            live = sum(
                t.name.startswith("ThreadPoolExecutor") for t in threading.enumerate()
            )
            line = {
                "at": datetime.now(UTC).strftime("%H:%M:%S"),
                "done": done,
                "of": len(jobs),
                "failed": failed,
                "workers_live": live,
                **result,
            }
            print(json.dumps(line), flush=True)
    if failed:
        raise SystemExit(f"{failed} units failed; rerun to retry them")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["frame", "current", "dated"])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/statewide_2021"))
    parser.add_argument("--posts", type=int, nargs="+", default=list(POSTS))
    parser.add_argument("--districts", type=int, nargs="+", default=list(range(1, 39)))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1 or any(p not in POSTS for p in args.posts):
        parser.error("Positive workers and post IDs 1, 2, 4, 5 or 6 required")
    if args.stage == "frame":
        build_frame(args.raw, args.workers)
    else:
        collect(args.raw, args.stage, args.posts, args.districts, args.workers)


if __name__ == "__main__":
    main()

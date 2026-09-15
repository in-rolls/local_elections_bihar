"""Collect by-elections held during the 2021–2026 term for all six offices.

The portal's by-election page drills from districts to seats for each office and
round (2023 phase 1, 2023 phase 2, 2025). Each listed seat's candidate list and
results are then requested from the by-election pages. build_2021.py parses them.
"""

import argparse
import concurrent.futures
import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from offices_2021 import order, request_params, unit_id
from sec_portal import decode_records, fetch

PHASES = ("2023_1", "2023_2", "2025_1")
ROOT = "byelections"


def details(raw, post, phase, level, d=0, b=0, p=0):
    body = fetch(
        raw,
        f"{ROOT}/listing/{phase}/p{post}/l{level}_d{d}_b{b}_p{p}",
        "ByElectionDetails",
        {
            "handler": "GetByElectionDetails",
            "DistrictId": d,
            "BlockId": b,
            "PanchayatId": p,
            "Level": level,
            "postId": post,
            "Phase": phase,
        },
    )
    return decode_records(body)


def seats_for(raw, post, phase, district):
    seats = []
    for block in details(raw, post, phase, 2, district):
        b = block["BlockID"]
        if post == 6:
            leaves = [
                {**leaf, "WardNo": leaf["JPN"]}
                for leaf in details(raw, post, phase, 3, district, b)
            ]
        else:
            leaves = [
                leaf
                for panchayat in details(raw, post, phase, 3, district, b)
                for leaf in details(
                    raw, post, phase, 4, district, b, panchayat["PanchayatID"]
                )
            ]
        for leaf in leaves:
            u = {
                "post_id": post,
                "district_id": district,
                "block_id": None if post == 6 else b,
                "panchayat_id": leaf.get("PanchayatID") if post < 5 else None,
                "seat_no": None if post in (3, 4) else int(leaf["WardNo"]),
            }
            seats.append(
                {
                    "phase": phase,
                    **u,
                    "unit_id": unit_id(u),
                    "district": leaf["DistrictName"],
                    "block": leaf["BlockName"],
                    "panchayat": leaf.get("PanchayatName") if post < 5 else None,
                }
            )
    return seats


def build_frame(raw, workers):
    jobs = []
    for post in range(1, 7):
        for phase in PHASES:
            districts = details(raw, post, phase, 1)
            listed = sum(int(x["Total"]) for x in districts)
            jobs += [(post, phase, x["Dist"], int(x["Total"])) for x in districts]
            print(json.dumps({"post": post, "phase": phase, "listed": listed}))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        groups = list(pool.map(lambda j: (j, seats_for(raw, *j[:3])), jobs))
    rows, gaps = {}, []
    for (post, phase, district, total), seats in groups:
        # A samiti seat spanning panchayats is listed once per panchayat.
        unique = {(s["phase"], s["post_id"], s["unit_id"]): s for s in seats}
        if len(unique) != total:
            gaps.append(
                {
                    "post": post,
                    "phase": phase,
                    "district": district,
                    "listed": total,
                    "seats": len(unique),
                }
            )
        rows.update(unique)
    print(json.dumps({"seats": len(rows), "district_count_gaps": gaps}))
    if gaps:
        raise ValueError("By-election seats differ from the listed district totals")
    (raw / ROOT).mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            sorted(rows.values(), key=lambda s: tuple(map(str, s.values())))
        ),
        raw / f"{ROOT}/frame.parquet",
    )


def fetch_seat(raw, u):
    params = request_params(u)
    base = f"{ROOT}/{u['phase']}/p{u['post_id']}"
    counts = {}
    for kind, page, handler in [
        ("candidates", "Bye/ContestingCandidates_C", "GetContestingCandidates"),
        ("results", "Bye/Result_C", "GetResult"),
    ]:
        body = fetch(
            raw,
            f"{base}/{kind}/{u['unit_id']}",
            page,
            {"handler": handler, **params, "phase": u["phase"]},
        )
        counts[kind] = len(decode_records(body))
    body = fetch(
        raw,
        f"{base}/phases/{u['unit_id']}",
        "Bye/Result_C",
        {"handler": "GetPhases", **params},
    )
    counts["phase_listed"] = any(x["i"] == u["phase"] for x in decode_records(body))
    return {"phase": u["phase"], "post": u["post_id"], "unit": u["unit_id"], **counts}


def collect(raw, workers):
    frame = order(pq.read_table(raw / f"{ROOT}/frame.parquet").to_pylist())
    failed = 0

    def run(u):
        try:
            return fetch_seat(raw, u)
        except Exception as error:
            return {"unit": u["unit_id"], "error": f"{type(error).__name__}: {error}"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for done, result in enumerate(pool.map(run, frame), 1):
            failed += "error" in result
            live = sum(
                t.name.startswith("ThreadPoolExecutor") for t in threading.enumerate()
            )
            print(
                json.dumps(
                    {
                        "at": datetime.now(UTC).strftime("%H:%M:%S"),
                        "done": done,
                        "of": len(frame),
                        "failed": failed,
                        "workers_live": live,
                        **result,
                    }
                ),
                flush=True,
            )
    if failed:
        raise SystemExit(f"{failed} seats failed; rerun to retry them")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["frame", "fetch"])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/statewide_2021"))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.stage == "frame":
        build_frame(args.raw, args.workers)
    else:
        collect(args.raw, args.workers)


if __name__ == "__main__":
    main()

"""Collect 2021 records for the five non-mukhiya offices; parse saved responses offline.

Offices (SEC post IDs): 1 ward member, 2 panch, 4 sarpanch, 5 panchayat samiti
member, 6 zila parishad member. Mukhiya (3) remains in sec_2021.py.
"""

import argparse
import base64
import collections
import concurrent.futures
import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from matching import match
from sec_portal import completed, decode_records, fetch

POSTS = (1, 2, 4, 5, 6)
WARD_POSTS = (1, 2)
PHASE = "2021_1"
TOTALS_URL = "https://sec25.bihar.gov.in/api/MapApi/districts"
ROOT = "2021/offices"


def unit_id(u):
    d, b, p, s = u["district_id"], u["block_id"], u["panchayat_id"], u["seat_no"]
    if u["post_id"] in WARD_POSTS:
        return f"d{d}_b{b}_p{p}_w{s}"
    if u["post_id"] == 4:
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


def clean_cell(row):
    """Source record as JSON, without the personal phone number."""
    return json.dumps(
        {k: v for k, v in row.items() if k != "MobileNo"}, ensure_ascii=False
    )


def event_rows(raw, key):
    event = completed(raw / f"{key}.jsonl.gz")
    if event is None:
        return None, None, None
    body = base64.b64decode(event["body_base64"])
    return event, hashlib.sha256(body).hexdigest(), decode_records(body)


def as_int(value):
    if value in (None, "", "NA"):
        return None
    if isinstance(value, bool):
        raise ValueError("Unexpected boolean identifier")
    return int(value)


UNIT_FIELDS = [
    ("post_id", pa.int8()),
    ("district_id", pa.int32()),
    ("block_id", pa.int32()),
    ("panchayat_id", pa.int64()),
    ("seat_no", pa.int32()),
    ("unit_id", pa.string()),
]


def write(out, name, rows, fields):
    schema = pa.schema(fields)
    path = out / f"{name}.parquet"
    temp = path.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), temp, compression="zstd")
    temp.replace(path)
    return {
        "path": path.name,
        "rows": len(rows),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schema": {f.name: str(f.type) for f in schema},
    }


def check_geography(u, row, path):
    """Every returned result row must name the seat that was requested."""
    got = (
        as_int(row["Dist"]),
        as_int(row["BlockID"]),
        as_int(row["PanchayatNo"]),
        as_int(row["WardNo"]),
    )
    d, b, p, s = u["district_id"], u["block_id"], u["panchayat_id"], u["seat_no"]
    post = u["post_id"]
    ok = got[0] == d and (
        (post in WARD_POSTS and got[1:] == (b, p, s))
        or (post == 4 and got[1:3] == (b, p))
        or (post == 5 and got[1] == b and got[3] == s)
        or (post == 6 and got[3] == s)
    )
    if not ok:
        raise ValueError(f"Result outside requested seat: {path} {got}")


def parse(raw, out):
    frame = pq.read_table(raw / f"{ROOT}/frame.parquet").to_pylist()
    candidates, results, coverage = [], [], []
    for u in frame:
        post, uid = u["post_id"], u["unit_id"]
        unit = {n: u[n] for n, _ in UNIT_FIELDS}
        base = f"{ROOT}/p{post}"
        c_event, c_sha, c_rows = event_rows(raw, f"{base}/candidates/{uid}")
        r_event, r_sha, r_rows = event_rows(raw, f"{base}/results/{uid}")
        p_event, _, p_rows = event_rows(raw, f"{base}/phases/{uid}")
        phase = (
            None
            if p_rows is None
            else any(x["i"] == PHASE and x["n"] == "2021" for x in p_rows)
        )
        for event in (c_event, r_event):
            if event is not None and event["params"]["phase"] != PHASE:
                raise ValueError(f"Unexpected election phase: {uid}")
        serials = collections.Counter()
        for i, row in enumerate(c_rows or [], 1):
            if as_int(row["PostId"]) != post:
                raise ValueError(f"Candidate office differs from request: {uid}")
            serials[as_int(row["OrderBy"])] += 1
            candidates.append(
                {
                    **unit,
                    "candidate_serial": as_int(row["OrderBy"]),
                    "candidate_name": row["CandidateName"],
                    "guardian_name": row.get("GaurdianName"),
                    "candidate_age": as_int(row.get("Age")),
                    "candidate_gender": row.get("Gender"),
                    "symbol": row.get("SymbolName"),
                    "affidavit_url": row.get("CandidateDoc"),
                    "photo_url": row.get("CandidatePhoto"),
                    "source_row": i,
                    "source_url": c_event["url"],
                    "fetched_at": c_event["fetched_at"],
                    "source_sha256": c_sha,
                    "raw_cell": clean_cell(row),
                }
            )
        listed = {as_int(r["OrderBy"]): r["CandidateName"] for r in c_rows or []}
        reported = {}
        for row in r_rows or []:
            reported.setdefault(as_int(row["OrderBy"]), row["CandidateName"])
        pairs = match(listed, reported)
        for i, row in enumerate(r_rows or [], 1):
            check_geography(u, row, uid)
            serial, method = pairs[as_int(row["OrderBy"])]
            results.append(
                {
                    **unit,
                    "result_serial": as_int(row["OrderBy"]),
                    "candidate_serial": serial,
                    "match_method": method,
                    "result_panchayat_id": as_int(row["PanchayatNo"]),
                    "result_panchayat": row.get("PanchayatName"),
                    "result_name": row["CandidateName"],
                    "votes": as_int(row.get("TotalVote")),
                    "elected": row.get("IsWin"),
                    "source_row": i,
                    "source_url": r_event["url"],
                    "fetched_at": r_event["fetched_at"],
                    "source_sha256": r_sha,
                    "raw_cell": clean_cell(row),
                }
            )
        coverage.append(
            {
                **unit,
                "district": u["district"],
                "block": u["block"],
                "panchayat": u["panchayat"],
                "candidates_fetched": c_event is not None,
                "results_fetched": r_event is not None,
                "phases_fetched": p_event is not None,
                "phase_2021_listed": phase,
                "candidate_records": len(c_rows or []),
                "repeated_candidate_serials": sum(n > 1 for n in serials.values()),
                "result_records": len(r_rows or []),
            }
        )
    out.mkdir(parents=True, exist_ok=True)
    unit_fields = list(UNIT_FIELDS)
    source_fields = [
        ("source_row", pa.int32()),
        ("source_url", pa.string()),
        ("fetched_at", pa.string()),
        ("source_sha256", pa.string()),
        ("raw_cell", pa.string()),
    ]
    files = [
        write(
            out,
            "candidates",
            candidates,
            unit_fields
            + [("candidate_serial", pa.int32())]
            + [(n, pa.string()) for n in ["candidate_name", "guardian_name"]]
            + [("candidate_age", pa.int32())]
            + [
                (n, pa.string())
                for n in ["candidate_gender", "symbol", "affidavit_url", "photo_url"]
            ]
            + source_fields,
        ),
        write(
            out,
            "result_rows",
            results,
            [
                *unit_fields,
                ("result_serial", pa.int32()),
                ("candidate_serial", pa.int32()),
                ("match_method", pa.string()),
                ("result_panchayat_id", pa.int64()),
                ("result_panchayat", pa.string()),
                ("result_name", pa.string()),
                ("votes", pa.int64()),
                ("elected", pa.bool_()),
                *source_fields,
            ],
        ),
        write(
            out,
            "coverage",
            coverage,
            unit_fields
            + [(n, pa.string()) for n in ["district", "block", "panchayat"]]
            + [
                (n, pa.bool_())
                for n in [
                    "candidates_fetched",
                    "results_fetched",
                    "phases_fetched",
                    "phase_2021_listed",
                ]
            ]
            + [
                (n, pa.int32())
                for n in [
                    "candidate_records",
                    "repeated_candidate_serials",
                    "result_records",
                ]
            ],
        ),
    ]
    files += parse_current(raw, out)
    (out / "MANIFEST.json").write_text(
        json.dumps({"phase": PHASE, "files": files}, indent=2, ensure_ascii=False)
        + "\n"
    )
    print(json.dumps({f["path"]: f["rows"] for f in files}))
    for name, rows, fields in [
        (
            "candidates",
            candidates,
            ["candidate_age", "candidate_gender", "guardian_name", "affidavit_url"],
        ),
        ("result_rows", results, ["votes", "elected"]),
    ]:
        by_post = collections.Counter(r["post_id"] for r in rows)
        fill = (
            {
                f: round(sum(r[f] not in (None, "") for r in rows) / len(rows), 4)
                for f in fields
            }
            if rows
            else {}
        )
        print(json.dumps({"table": name, "by_post": by_post, "fill": fill}))


def parse_current(raw, out):
    files = []
    for kind in ("winners", "reservations"):
        rows = []
        for path in sorted((raw / f"current/{kind}").glob("p*/*.jsonl.gz")):
            post = int(path.parent.name[1:])
            key = path.relative_to(raw).as_posix().removesuffix(".jsonl.gz")
            event, sha, records = event_rows(raw, key)
            if event is None:
                continue
            ids = {
                part[0]: int(part[1:])
                for part in path.name.removesuffix(".jsonl.gz").split("_")
            }
            for i, row in enumerate(records, 1):
                if as_int(row["Dist"]) != ids["d"]:
                    raise ValueError(f"Current feed outside request: {path}")
                if as_int(row["BlockID"]) != ids["b"]:
                    # The zila parishad reservation feed ignores BlockID and returns
                    # the whole district to every block request; each seat is kept
                    # once, from the request for the block it is listed under.
                    if (post, kind) == (6, "reservations"):
                        continue
                    raise ValueError(f"Current feed outside request: {path}")
                if "p" in ids and as_int(row["PanchayatNo"]) != ids["p"]:
                    raise ValueError(f"Current feed outside panchayat: {path}")
                rows.append(
                    {
                        "post_id": post,
                        "district_id": ids["d"],
                        "block_id": ids["b"],
                        "panchayat_id": as_int(row["PanchayatNo"]),
                        "seat_no": as_int(row["WardNo"]),
                        "post": row.get("Post"),
                        "candidate_name": row.get("CandidateName"),
                        "guardian_name": row.get("GuardianName"),
                        "candidate_age": as_int(row.get("Age")),
                        "candidate_gender": row.get("Gender"),
                        "candidate_category": row.get("Category"),
                        "reservation_for_reported": row.get("ReservationFor"),
                        "reservation_status_reported": row.get("ReservationStatus"),
                        "seat_reservation": row.get("Reservation"),
                        "affidavit_url": row.get("Affidavit"),
                        "photo_url": row.get("CandidatePhotos"),
                        "source_row": i,
                        "source_url": event["url"],
                        "fetched_at": event["fetched_at"],
                        "source_sha256": sha,
                        "raw_cell": clean_cell(row),
                    }
                )
        strings = [
            "post",
            "candidate_name",
            "guardian_name",
            "candidate_gender",
            "candidate_category",
            "reservation_for_reported",
            "reservation_status_reported",
            "seat_reservation",
            "affidavit_url",
            "photo_url",
        ]
        fields = (
            [
                ("post_id", pa.int8()),
                ("district_id", pa.int32()),
                ("block_id", pa.int32()),
                ("panchayat_id", pa.int64()),
                ("seat_no", pa.int32()),
                ("candidate_age", pa.int32()),
            ]
            + [(n, pa.string()) for n in strings]
            + [
                ("source_row", pa.int32()),
                ("source_url", pa.string()),
                ("fetched_at", pa.string()),
                ("source_sha256", pa.string()),
                ("raw_cell", pa.string()),
            ]
        )
        files.append(write(out, f"current_{kind}", rows, fields))
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["frame", "current", "dated", "parse"])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/statewide_2021"))
    parser.add_argument("--out", type=Path, default=Path("data/interim/2021/offices"))
    parser.add_argument("--posts", type=int, nargs="+", default=list(POSTS))
    parser.add_argument("--districts", type=int, nargs="+", default=list(range(1, 39)))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1 or any(p not in POSTS for p in args.posts):
        parser.error("Positive workers and post IDs 1, 2, 4, 5 or 6 required")
    if args.stage == "frame":
        build_frame(args.raw, args.workers)
    elif args.stage == "parse":
        parse(args.raw, args.out)
    else:
        collect(args.raw, args.stage, args.posts, args.districts, args.workers)


if __name__ == "__main__":
    main()

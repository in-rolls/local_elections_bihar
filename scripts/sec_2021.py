"""Collect explicit-2021 mukhiya records; parse saved responses offline."""

import argparse
import base64
import concurrent.futures
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from sec_portal import completed, decode_records, fetch


def collect(raw, districts, workers):
    frame = pq.read_table(raw / "frame.parquet").to_pylist()
    blocks = [u for u in frame if u["post_id"] == 3 and u["district_id"] in districts]

    def units(u):
        d, b = u["district_id"], u["block_id"]
        body = fetch(
            raw,
            f"2021/frame/d{d}_b{b}",
            "Result",
            {"handler": "GetPanchayats", "districtId": d, "blockId": b},
        )
        return [
            {**u, "panchayat_id": p["i"], "panchayat": p["n"]}
            for p in decode_records(body)
        ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        frame_2021 = [u for group in pool.map(units, blocks) for u in group]
    frame_path = raw / "2021/frame.parquet"
    if frame_path.exists():
        frame_2021 += [
            u
            for u in pq.read_table(frame_path).to_pylist()
            if u["district_id"] not in districts
        ]
    pq.write_table(pa.Table.from_pylist(frame_2021), frame_path)

    def unit(u):
        d, b, p = u["district_id"], u["block_id"], int(u["panchayat_id"])
        params = {
            "postId": 3,
            "districtId": d,
            "blockId": b,
            "panchayatId": p,
            "ward": "",
            "psn": -1,
            "jpn": -1,
        }
        phases = decode_records(
            fetch(
                raw,
                f"2021/phases/d{d}_b{b}_p{p}",
                "Result",
                {"handler": "GetPhases", **params},
            )
        )
        if not any(x["i"] == "2021_1" and x["n"] == "2021" for x in phases):
            return {
                "district": d,
                "block": b,
                "panchayat": p,
                "reason": "2021 phase absent",
            }
        counts = {}
        for kind, page, handler in [
            ("results", "Result", "GetResult"),
            ("candidates", "ContestingCandidates", "GetContestingCandidates"),
        ]:
            body = fetch(
                raw,
                f"2021/{kind}/d{d}_b{b}_p{p}",
                page,
                {"handler": handler, **params, "phase": "2021_1"},
            )
            counts[kind] = len(decode_records(body))
        return {"district": d, "block": b, "panchayat": p, **counts}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(
            unit, [u for u in frame_2021 if u["district_id"] in districts]
        ):
            print(json.dumps(result), flush=True)


def parse(raw, out):
    frame = pq.read_table(raw / "2021/frame.parquet").to_pylist()
    output = []
    for u in frame:
        d, b, p = u["district_id"], u["block_id"], int(u["panchayat_id"])
        for kind in ("results", "candidates"):
            event = completed(raw / f"2021/{kind}/d{d}_b{b}_p{p}.jsonl.gz")
            if event is None:
                continue
            if event["params"]["phase"] != "2021_1":
                raise ValueError("Unexpected election phase")
            body = base64.b64decode(event["body_base64"])
            for i, row in enumerate(decode_records(body), 1):
                if kind == "results" and (
                    row["Dist"],
                    row["BlockID"],
                    row["PanchayatNo"],
                ) != (d, b, p):
                    raise ValueError("Results outside requested geography")
                output.append(
                    {
                        "district_id": d,
                        "block_id": b,
                        "panchayat_id": p,
                        "post_id": 3,
                        "year": 2021,
                        "kind": kind,
                        "source_row": i,
                        "candidate_serial": row["OrderBy"],
                        "candidate_name": row["CandidateName"],
                        "candidate_age": row.get("Age"),
                        "candidate_gender": row.get("Gender"),
                        "votes": row.get("TotalVote"),
                        "elected": row.get("IsWin"),
                        "affidavit_url": row.get("CandidateDoc"),
                        "source_url": event["url"],
                        "fetched_at": event["fetched_at"],
                        "source_sha256": hashlib.sha256(body).hexdigest(),
                        "raw_cell": json.dumps(row, ensure_ascii=False),
                    }
                )
    integers = [
        "district_id",
        "block_id",
        "panchayat_id",
        "post_id",
        "year",
        "source_row",
        "candidate_serial",
        "candidate_age",
        "votes",
    ]
    strings = [
        "kind",
        "candidate_name",
        "candidate_gender",
        "affidavit_url",
        "source_url",
        "fetched_at",
        "source_sha256",
        "raw_cell",
    ]
    schema = pa.schema(
        [(n, pa.int64()) for n in integers]
        + [("elected", pa.bool_())]
        + [(n, pa.string()) for n in strings]
    )
    out.mkdir(parents=True, exist_ok=True)
    path = out / "mukhiya_2021.parquet"
    pq.write_table(
        pa.Table.from_pylist(output, schema=schema), path, compression="zstd"
    )
    manifest = {
        "rows": len(output),
        "districts": sorted({r["district_id"] for r in output}),
        "panchayats_enumerated": len(frame),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schema": {f.name: str(f.type) for f in schema},
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["fetch", "parse"])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/portal_2021_2026"))
    parser.add_argument("--out", type=Path, default=Path("data/fin/2021"))
    parser.add_argument("--districts", type=int, nargs="+", default=[33])
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.stage == "fetch":
        collect(args.raw, args.districts, args.workers)
    else:
        parse(args.raw, args.out)


if __name__ == "__main__":
    main()

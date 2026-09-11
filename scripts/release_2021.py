"""Build and verify the declared 2021 state release from saved SEC responses."""

import argparse
import collections
import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from sec_2021 import parse
from sec_portal import completed

KEY = ["district_id", "block_id", "panchayat_id", "candidate_serial"]
SEAT = KEY[:-1]


def key(row, fields=KEY):
    return tuple(int(row[n]) for n in fields)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(out, name, rows, fields):
    schema = pa.schema(fields)
    path = out / f"{name}.parquet"
    temp = path.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), temp, compression="zstd")
    temp.replace(path)
    return {
        "path": path.name,
        "rows": len(rows),
        "sha256": sha(path),
        "schema": {f.name: str(f.type) for f in schema},
    }


def build(raw, parsed, out):
    parse(raw, parsed)
    frame = pq.read_table(raw / "2021/frame.parquet").to_pylist()
    units = {key(r, SEAT): r for r in frame}
    if len(units) != len(frame):
        raise ValueError("Duplicate geographic frame key")
    feeds = {"candidates": {}, "results": {}}
    for row in pq.read_table(parsed / "mukhiya_2021.parquet").to_pylist():
        k = key(row)
        if k in feeds[row["kind"]]:
            raise ValueError("Duplicate candidacy key within feed")
        if k[:3] not in units:
            raise ValueError("Record outside geographic frame")
        feeds[row["kind"]][k] = row
    c, r = feeds["candidates"], feeds["results"]
    if r.keys() - c.keys():
        raise ValueError("Result records without candidate-list matches")
    coverage, receipts = [], []
    counts = {
        kind: collections.Counter(k[:3] for k in feed) for kind, feed in feeds.items()
    }
    winners = collections.Counter(
        k[:3] for k, row in r.items() if row["elected"] is True
    )
    for k, unit in sorted(units.items()):
        d, b, p = k
        status = {}
        for kind in feeds:
            path = raw / f"2021/{kind}/d{d}_b{b}_p{p}.jsonl.gz"
            event = completed(path)
            if event is None:
                raise ValueError(f"Incomplete production checkpoint: {path}")
            status[kind] = "records" if counts[kind][k] else "empty_response"
            receipts.append(
                {
                    "path": path.relative_to(raw).as_posix(),
                    "sha256": sha(path),
                    "source_url": event["url"],
                    "fetched_at": event["fetched_at"],
                }
            )
        if winners[k] > 1:
            raise ValueError("Conflicting winner flags")
        coverage.append(
            {
                **dict(zip(SEAT, k, strict=True)),
                **{n: unit[n] for n in ["district", "block", "panchayat"]},
                "candidate_records": counts["candidates"][k],
                "result_records": counts["results"][k],
                "winner_records": winners[k],
                "candidate_status": status["candidates"],
                "result_status": status["results"],
                "winner_status": "flagged"
                if winners[k]
                else ("no_winner_flag" if counts["results"][k] else "empty_results"),
            }
        )
    records = []
    for k, candidate in sorted(c.items()):
        result = r.get(k, {})
        unit = units[k[:3]]
        records.append(
            {
                **candidate,
                **{n: unit[n] for n in ["district", "block", "panchayat"]},
                "document_id": "_".join(map(str, k)),
                "result_present": k in r,
                "votes": result.get("votes"),
                "elected": result.get("elected"),
                "result_name": result.get("candidate_name"),
                "result_source_url": result.get("source_url"),
                "result_source_sha256": result.get("source_sha256"),
                "result_source_row": result.get("source_row"),
                "result_raw_cell": result.get("raw_cell"),
            }
        )
    out.mkdir(parents=True, exist_ok=True)
    strings = [
        "document_id",
        "district",
        "block",
        "panchayat",
        "candidate_name",
        "candidate_gender",
        "affidavit_url",
        "source_url",
        "fetched_at",
        "source_sha256",
        "raw_cell",
        "result_name",
        "result_source_url",
        "result_source_sha256",
        "result_raw_cell",
    ]
    fields = [
        (n, pa.int64())
        for n in [
            *KEY,
            "year",
            "post_id",
            "candidate_age",
            "votes",
            "source_row",
            "result_source_row",
        ]
    ]
    fields += [(n, pa.string()) for n in strings]
    fields += [(n, pa.bool_()) for n in ["result_present", "elected"]]
    files = [
        table(out, "gp_head_candidates_2021", records, fields),
        table(
            out,
            "gp_head_winner_records_2021",
            [x for x in records if x["elected"] is True],
            fields,
        ),
    ]
    coverage_fields = [
        (n, pa.int64())
        for n in [*SEAT, "candidate_records", "result_records", "winner_records"]
    ]
    coverage_fields += [
        (n, pa.string())
        for n in [
            "district",
            "block",
            "panchayat",
            "candidate_status",
            "result_status",
            "winner_status",
        ]
    ]
    files.append(table(out, "coverage", coverage, coverage_fields))
    validation = {
        "candidate_records": len(c),
        "result_records": len(r),
        "candidate_only_records": len(c.keys() - r.keys()),
        "result_only_records": len(r.keys() - c.keys()),
        "panchayats_enumerated": len(units),
        "districts": len({k[0] for k in units}),
        "blocks": len({k[:2] for k in units}),
        "winner_records": sum(winners.values()),
        "winner_status": dict(
            collections.Counter(x["winner_status"] for x in coverage)
        ),
        "candidate_gender_raw": dict(
            collections.Counter(x["candidate_gender"] for x in records)
        ),
        "winner_missing_affidavit_url": sum(
            not x["affidavit_url"] for x in records if x["elected"] is True
        ),
    }
    for path in sorted((raw / "2021").glob("*/*.jsonl.gz")):
        if path.parent.name in feeds:
            continue
        event = completed(path)
        if event is None:
            raise ValueError(f"Incomplete frame/phase checkpoint: {path}")
        receipts.append(
            {
                "path": path.relative_to(raw).as_posix(),
                "sha256": sha(path),
                "source_url": event["url"],
                "fetched_at": event["fetched_at"],
            }
        )
    dictionary = {
        "document_id": (
            "Full geographic key and candidate serial joined by underscores; "
            "no cross-year identity."
        ),
        "elected": (
            "Source IsWin flag; null when no result record exists. Never "
            "inferred from votes or gender."
        ),
        "result_present": "Candidate key occurs in the result feed.",
        "votes": "Source TotalVote; null when no result record exists.",
        "winner_status": (
            "flagged, no_winner_flag, or empty_results; absence is not a "
            "vacancy finding."
        ),
        "candidate_status": (
            "records or empty_response from a completed candidate request."
        ),
        "result_status": "records or empty_response from a completed result request.",
    }
    with (out / "dictionary.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["table", "column", "type", "definition", "missing"])
        for info in files:
            for name, dtype in info["schema"].items():
                definition = dictionary.get(name)
                if definition is None:
                    if name in KEY:
                        definition = "ID scoped by year, office and full geography."
                    elif name in ["year", "post_id"]:
                        definition = (
                            "Explicit request scope: year 2021 and mukhiya post 3."
                        )
                    elif name in ["district", "block", "panchayat"]:
                        definition = "Unmodified name from the portal geographic frame."
                    elif name.endswith("raw_cell"):
                        definition = "Unmodified source record serialized as JSON."
                    elif name.endswith("sha256"):
                        definition = "SHA256 of saved source response bytes."
                    elif name.endswith("source_url"):
                        definition = (
                            "SEC request URL including election phase and geographic "
                            "parameters."
                        )
                    elif name.endswith("source_row"):
                        definition = "One-based record position within that response."
                    elif name.endswith("records"):
                        definition = (
                            "Feed count for this panchayat; zero means an "
                            "empty response."
                        )
                    elif name == "fetched_at":
                        definition = (
                            "UTC acquisition timestamp of candidate source response."
                        )
                    elif name == "affidavit_url":
                        definition = "CandidateDoc PDF link supplied in candidate list."
                    else:
                        definition = (
                            "Source-reported "
                            + name.replace("_", " ")
                            + "; no imputation."
                        )
                writer.writerow(
                    [
                        info["path"],
                        name,
                        dtype,
                        definition,
                        "null means unavailable, never zero",
                    ]
                )
    manifest = {
        "schema_version": 1,
        "year": 2021,
        "source_phase": "2021_1",
        "code_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "parser_sha256": {
            p.name: sha(p)
            for p in [Path(__file__), Path(__file__).with_name("sec_2021.py")]
        },
        "grain": {
            files[0][
                "path"
            ]: "candidate within year, office and full geographic/serial key",
            files[1][
                "path"
            ]: "source-flagged winner within year, office and full geography",
            files[2]["path"]: "enumerated panchayat, including empty responses",
        },
        "keys": {files[0]["path"]: KEY, files[1]["path"]: SEAT, files[2]["path"]: SEAT},
        "files": files,
        "validation": validation,
        "input_frame_sha256": sha(raw / "2021/frame.parquet"),
        "inputs": receipts,
        "limitations": [
            "Enumeration uses the portal frame retrieved in 2026; "
            "it is not an independent 2021 seat census.",
            "Current 2021–2026 reservations excluded: election year unstated.",
            "Education is released separately; unavailable values must remain unknown.",
        ],
    }
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    (out / "SCHEMA.json").write_text(
        json.dumps({f["path"]: f["schema"] for f in files}, indent=2) + "\n"
    )
    (out / "validation.json").write_text(
        json.dumps(validation, indent=2, ensure_ascii=False) + "\n"
    )
    (out / "CHECKSUMS").write_text(
        "".join(f"{f['sha256']}  {f['path']}\n" for f in files)
    )
    print(json.dumps(validation, ensure_ascii=False))
    verify(out)


def verify(out):
    manifest = json.loads((out / "MANIFEST.json").read_text())
    for info in manifest["files"]:
        path = out / info["path"]
        if sha(path) != info["sha256"]:
            raise ValueError(f"Changed release checksum: {path}")
        data = pq.read_table(path)
        if (
            len(data) != info["rows"]
            or {f.name: str(f.type) for f in data.schema} != info["schema"]
        ):
            raise ValueError(f"Changed release rows or schema: {path}")
        keys = [key(row, manifest["keys"][info["path"]]) for row in data.to_pylist()]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate release key: {path}")
    c = pq.read_table(out / "gp_head_candidates_2021.parquet").to_pylist()
    w = pq.read_table(out / "gp_head_winner_records_2021.parquet").to_pylist()
    coverage = pq.read_table(out / "coverage.parquet").to_pylist()
    if [x for x in c if x["elected"] is True] != w:
        raise ValueError("Winner export differs from result flags")
    if sum(x["candidate_records"] for x in coverage) != len(c):
        raise ValueError("Candidate coverage does not reconcile")
    if sum(x["winner_records"] for x in coverage) != len(w):
        raise ValueError("Winner coverage does not reconcile")
    if any(
        x["elected"] is not None or x["votes"] is not None
        for x in c
        if not x["result_present"]
    ):
        raise ValueError("Missing results converted to observed outcomes")
    print(json.dumps({"verified": True, "files": len(manifest["files"])}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/statewide_2021"))
    parser.add_argument("--parsed", type=Path, default=Path("data/interim/2021/parsed"))
    parser.add_argument("--out", type=Path, default=Path("data/release/2021"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        verify(args.out)
    else:
        build(args.raw, args.parsed, args.out)


if __name__ == "__main__":
    main()

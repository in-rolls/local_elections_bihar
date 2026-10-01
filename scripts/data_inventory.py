"""Summarize and verify the local data migration receipts without network access."""

import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from itertools import batched
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "data/MIGRATION.csv.gz"
PRUNING = ROOT / "data/PRUNING.csv.gz"


def read_inventory(receipt, pruning=None):
    """Collapse historical aliases while rejecting conflicting destination hashes."""
    records = {}
    with gzip.open(receipt, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            path = PurePosixPath(row["canonical_path"])
            if (
                not path.parts
                or path.is_absolute()
                or ".." in path.parts
                or path.parts[0] != "data"
            ):
                raise ValueError(f"Unsafe inventory path: {path}")
            if len(path.parts) < 4 or path.parts[2] not in {"raw", "interim"}:
                raise ValueError(f"Unexpected inventory location: {path}")
            row["bytes"] = int(row["bytes"])
            previous = records.get(str(path))
            if previous and (previous["sha256"], previous["bytes"]) != (
                row["sha256"],
                row["bytes"],
            ):
                raise ValueError(f"Conflicting inventory entries: {path}")
            records[str(path)] = {
                key: row[key] for key in ("canonical_path", "bytes", "sha256")
            }
    if not records:
        raise ValueError("Empty inventory")
    if pruning is not None:
        with gzip.open(pruning, "rt", newline="") as handle:
            for row in csv.DictReader(handle):
                previous = records.pop(row["canonical_path"], None)
                if previous is None or (previous["sha256"], previous["bytes"]) != (
                    row["sha256"],
                    int(row["bytes"]),
                ):
                    raise ValueError(
                        f"Pruning receipt mismatch: {row['canonical_path']}"
                    )
    return records


def check_file(root, row):
    path = root / row["canonical_path"]
    try:
        if path.stat().st_size != row["bytes"]:
            return f"size differs: {row['canonical_path']}"
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != row["sha256"]:
            return f"checksum differs: {row['canonical_path']}"
    except OSError as error:
        return f"unavailable: {row['canonical_path']}: {error}"
    return None


def verify(root, records, workers=8):
    failures = []
    count = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for batch in batched(records.values(), 512):
            for result in pool.map(lambda row: check_file(root, row), batch):
                count += 1
                if result:
                    failures.append(result)
            if count % 10240 == 0:
                print(
                    json.dumps({"checked": count, "failures": len(failures)}),
                    flush=True,
                )
    if failures:
        raise ValueError("\n".join(failures[:20]) + f"\n{len(failures)} failures")
    print(json.dumps({"verified_files": count}))


def summary(records, out):
    """Generate asset sizes from receipts, without opening the large source trees."""
    groups = defaultdict(lambda: {"files": 0, "bytes": 0, "archive_bytes": 0})
    for row in records.values():
        path = PurePosixPath(row["canonical_path"])
        asset = "/".join(path.parts[:4])
        group = groups[asset]
        group["files"] += 1
        group["bytes"] += row["bytes"]
        if path.name.endswith((".tar", ".tar.gz", ".zip", ".7z")):
            group["archive_bytes"] += row["bytes"]
    rows = []
    for asset, counts in sorted(groups.items()):
        _, year, role, _ = asset.split("/")
        rows.append(
            {
                "path": asset,
                "year": year,
                "role": role,
                **counts,
                "availability": (
                    "Zenodo 22852474 publication metadata; payload copies pruned"
                    if asset == "data/2016/interim/zenodo_export"
                    else "local; distribution decision pending"
                ),
            }
        )
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    years = defaultdict(lambda: defaultdict(int))
    deferred = defaultdict(int)
    archives = []
    file_types = defaultdict(lambda: {"files": 0, "bytes": 0})
    core_types = defaultdict(lambda: {"files": 0, "bytes": 0})
    for row in records.values():
        path = PurePosixPath(row["canonical_path"])
        year, role, asset = path.parts[1:4]
        years[year][f"{role}_bytes"] += row["bytes"]
        years[year][f"{role}_files"] += 1
        is_deferred = year == "2021" and (
            asset in {"affidavits", "vision_validation", "source_search"}
            or (role == "interim" and asset != "archive")
        )
        extension = (
            "jsonl.gz"
            if path.name.endswith(".jsonl.gz")
            else "html.gz"
            if path.name.endswith(".html.gz")
            else path.suffix.lstrip(".") or "no_extension"
        )
        file_types[extension]["files"] += 1
        file_types[extension]["bytes"] += row["bytes"]
        if not is_deferred:
            core_types[extension]["files"] += 1
            core_types[extension]["bytes"] += row["bytes"]
        if is_deferred:
            deferred[f"{role}_bytes"] += row["bytes"]
            deferred[f"{role}_files"] += 1
        if path.name.endswith((".tar", ".tar.gz", ".zip", ".7z")):
            archives.append(
                {"path": str(path), "bytes": row["bytes"], "sha256": row["sha256"]}
            )
    organization = out.parent / "provenance/organization.json"
    migration = json.loads(organization.read_text()) if organization.exists() else {}
    report = {
        "measurement": "File bytes, not disk allocation or future compressed sizes",
        "files": len(records),
        "total_bytes": sum(row["bytes"] for row in records.values()),
        "by_year": dict(years),
        "by_file_type": dict(sorted(file_types.items())),
        "outside_deferred_by_file_type": dict(sorted(core_types.items())),
        "outside_deferred_bytes": sum(x["bytes"] for x in core_types.values()),
        "deferred_affidavit_and_education_work": dict(deferred),
        "archive_files": sorted(archives, key=lambda row: row["bytes"], reverse=True),
        "duplicate_copies_removed": migration.get("duplicates"),
        "duplicate_bytes_saved": migration.get("bytes_saved"),
        "published_tables": "Excluded; tracked separately in data/2016 and data/2021",
        "remote_actions": "None; existing Zenodo publication verified separately",
        "pruning": (
            json.loads((out.parent / "provenance/pruning.json").read_text())
            if (out.parent / "provenance/pruning.json").exists()
            else None
        ),
    }
    out.with_name("SIZE_REPORT.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"assets": len(rows), "bytes": report["total_bytes"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify", "summary"])
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    parser.add_argument("--pruning", type=Path, default=PRUNING)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--year", choices=["2006", "2011", "2016", "2021", "undated"])
    parser.add_argument("--role", choices=["raw", "interim"])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, default=ROOT / "data/CATALOG.csv")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    records = read_inventory(args.receipt, args.pruning)
    records = {
        key: row
        for key, row in records.items()
        if (args.year is None or PurePosixPath(key).parts[1] == args.year)
        and (args.role is None or PurePosixPath(key).parts[2] == args.role)
    }
    if not records:
        parser.error("No inventory entries match the selection")
    if args.action == "verify":
        verify(args.root, records, args.workers)
    else:
        summary(records, args.out)


if __name__ == "__main__":
    main()

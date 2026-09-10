"""Stream Bihar's historical candidate CSVs to documented Parquet files."""

import argparse
import csv
import hashlib
import json
from itertools import islice
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONTRACTS = json.loads((ROOT / "schemas.json").read_text())
BATCH_SIZE = 5000


def schema(contract):
    return pa.schema(
        [pa.field("year", pa.int16(), nullable=False)]
        + [pa.field(name, pa.string()) for name in contract["columns"]]
        + [
            pa.field("source_row", pa.int32(), nullable=False),
            pa.field("duplicate_of_source_row", pa.int32()),
            pa.field("candidate_missing", pa.bool_(), nullable=False),
        ]
    )


def records(path, contract):
    """Retain every row, marking later exact copies and missing names."""
    seen = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        if next(reader, None) != contract["columns"]:
            raise ValueError(f"{path}: unexpected header")
        count = 0
        for number, values in enumerate(reader, 1):
            if len(values) != len(contract["columns"]):
                raise ValueError(f"{path}:{number}: inconsistent column count")
            row = dict(zip(contract["columns"], values, strict=True))
            if row["post"] != contract["post"]:
                raise ValueError(f"{path}:{number}: unexpected post")
            fingerprint = hashlib.sha256(
                json.dumps(values, ensure_ascii=False).encode()
            ).digest()
            duplicate = seen.get(fingerprint)
            seen.setdefault(fingerprint, number)
            missing = not row["candidate_name"].strip()
            row = {name: value or None for name, value in row.items()}
            row.update(
                year=contract["year"],
                source_row=number,
                duplicate_of_source_row=duplicate,
                candidate_missing=missing,
            )
            count += 1
            yield row
        if not count:
            raise ValueError(f"{path}: no candidate rows")


def batches(path, contract):
    reader = records(path, contract)
    while chunk := list(islice(reader, BATCH_SIZE)):
        yield pa.RecordBatch.from_pylist(chunk, schema=schema(contract))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def convert(source, target, contract, check=False):
    counts = {"rows": 0, "duplicate_rows": 0, "missing_candidates": 0}
    expected_schema = schema(contract)
    temporary = target.with_suffix(".parquet.part")
    target.parent.mkdir(parents=True, exist_ok=True)
    if check:
        saved = pq.ParquetFile(target)
        if not saved.schema_arrow.equals(expected_schema, check_metadata=True):
            raise ValueError(f"{target}: schema differs from contract")
        actual = saved.iter_batches(batch_size=BATCH_SIZE)
        writer = None
    else:
        actual = None
        writer = pq.ParquetWriter(temporary, expected_schema, compression="zstd")
    try:
        for batch in batches(source, contract):
            if check:
                other = next(actual, None)
                if other is None or not batch.equals(other, check_metadata=True):
                    raise ValueError(f"{target}: rows differ from source CSV")
            else:
                writer.write_batch(batch)
            counts["rows"] += batch.num_rows
            counts["duplicate_rows"] += (
                batch.num_rows - batch.column("duplicate_of_source_row").null_count
            )
            counts["missing_candidates"] += sum(
                batch.column("candidate_missing").to_pylist()
            )
        if check and next(actual, None) is not None:
            raise ValueError(f"{target}: extra rows beyond source CSV")
        if writer:
            writer.close()
            temporary.replace(target)
        return counts
    finally:
        if writer:
            writer.close()
            temporary.unlink(missing_ok=True)


def export(data, out, check=False):
    manifest = {
        "format_version": 1,
        "column_contract_sha256": digest(ROOT / "schemas.json"),
        "files": [],
    }
    for name, contract in CONTRACTS.items():
        source, target = data / name, out / contract["output"]
        counts = convert(source, target, contract, check)
        manifest["files"].append(
            {
                "file": target.name,
                "source_csv": name,
                "source_sha256": digest(source),
                "sha256": digest(target),
                **counts,
                "schema": [
                    {"name": f.name, "type": str(f.type), "nullable": f.nullable}
                    for f in schema(contract)
                ],
            }
        )
        print(
            f"{target.name}: {counts['rows']:,} rows; "
            f"{counts['duplicate_rows']:,} later exact copies; "
            f"{counts['missing_candidates']} missing names"
        )
    path = out / "MANIFEST.json"
    if check:
        if json.loads(path.read_text()) != manifest:
            raise ValueError(f"{path}: source hashes or manifest metadata changed")
    else:
        temporary = path.with_suffix(".json.part")
        temporary.write_text(json.dumps(manifest, indent=2) + "\n")
        temporary.replace(path)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        export(args.data, args.out or args.data / "fin", args.check)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()

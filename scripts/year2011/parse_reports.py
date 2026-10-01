"""Parse the collected 2011 district Mukhiya winner reports with source receipts."""

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.year2011.parse_gaya import (
    DESCRIPTIONS,
    FIELDS,
    ROOT,
    YEAR_ASSIGNMENT,
    YEAR_RECEIPT,
    pdf_winners,
    write_csv,
)

CATEGORY_LABELS = {
    "unreserved": {"अनारक्षित", "सामान्य", "अना0", "सा0"},
    "SC": {"अनुसूचितजाति", "अनुसुचितजाति", "अनु0जाति", "अनु0जाती", "आरक्षितअनु0जाति"},
    "ST": {"अनुसूचितजनजाति", "अनुसुचितजनजाति", "अनु0जनजाति"},
    "BC": {"पिछडावर्ग", "पिछड़ावर्ग", "पि0वर्ग", "पि0व0", "आरक्षितपि0वर्ग"},
    "EBC": {
        "अतिपिछडावर्ग",
        "अतिपिछड़ावर्ग",
        "अत्यन्तपिछडावर्ग",
        "अत्यंतपिछडावर्ग",
        "अत्यंतपिछड़ावर्ग",
    },
}
GENDERS = {
    "महिला": "female",
    "महीला": "female",
    "पुरुष": "male",
    "पुरूष": "male",
    "अन्य": "other",
}
NUMBERS = ("age", "annual_income", "sons", "daughters")
INTS = {
    "collection_year",
    "election_year",
    "source_serial",
    "source_page",
    "decode_issue_count",
    *NUMBERS,
}
BOOLS = {
    "reservation_women",
    "missing_block",
    "seat_label_repeated",
    "name_within_block_repeated",
}
DESCRIPTIONS = {
    **DESCRIPTIONS,
    "district_raw": "District folder label; source file/page retained for verification",
    "block": "Hindi crosswalk available for Gaya only; otherwise null",
    "election_year": (
        "2011, based on maintainer confirmation and prior-election headings"
    ),
    "gender": "female/male/other from explicit source labels; no name inference",
    "seat_label_repeated": (
        "Repeated literal block/panchayat label within district; "
        "null if either label is missing"
    ),
    "name_within_block_repeated": (
        "Repeated literal name within district/block; null if name or block missing"
    ),
    "duplicate_of_record_id": (
        "First record with identical decoded source cells and block in this PDF; "
        "null for first occurrence or any decoding failure"
    ),
    "reservation_category": (
        "Exact reviewed source-label mapping to unreserved/SC/ST/BC/EBC; "
        "ambiguous labels null"
    ),
    "reservation_women": (
        "True for explicit female label; false for explicit other/male; otherwise null"
    ),
    "decode_issue_count": (
        "Cells set to null because glyph ordering could not be resolved; see issues.csv"
    ),
    "missing_block": (
        "No readable block label recovered from heading; no carry-forward "
        "or address-based inference"
    ),
    "year_basis": ("Year evidence; see data/PROVENANCE.json"),
}


def reservation(value):
    """Map explicit text only; keep BC and EBC distinct as the source writes them."""
    text = re.sub(r"[\s,./()\-]", "", (value or "").replace("\u0966", "0"))
    female = any(word in text for word in ("महिला", "महीला"))
    other = any(word in text for word in ("अन्य", "पुरुष", "पुरूष"))
    women = None if female == other else female
    for suffix in ("महिला", "महीला", "अन्य", "पुरुष", "पुरूष"):
        text = text.removesuffix(suffix)
    category = next(
        (key for key, values in CATEGORY_LABELS.items() if text in values), None
    )
    return category, women


def release_records(records):
    """Keep located, named winners once; retain source-row evidence for exclusions."""
    kept, exclusions = [], []
    duplicates = 0
    for row in records:
        missing = [
            key
            for key in ["district_raw", "block_raw", "panchayat_raw", "candidate_name"]
            if not (row[key] or "").strip()
        ]
        if missing:
            exclusions.append(
                {
                    "source_file": row["source_file"],
                    "source_serial": row["source_serial"],
                    "source_page": row["source_page"],
                    "field": ",".join(missing),
                    "kind": "excluded_missing_location_or_name",
                    "detail": (
                        "Required source label missing; "
                        "no verified replacement supplied"
                    ),
                    "source_box": row["source_box"],
                }
            )
        elif row["duplicate_of_record_id"] is not None:
            duplicates += 1
        else:
            kept.append(dict(row))
    seats = collections.Counter(
        (r["district_raw"], r["block_raw"], r["panchayat_raw"]) for r in kept
    )
    names = collections.Counter(
        (r["district_raw"], r["block_raw"], r["candidate_name"]) for r in kept
    )
    for row in kept:
        row["seat_label_repeated"] = (
            seats[(row["district_raw"], row["block_raw"], row["panchayat_raw"])] > 1
        )
        row["name_within_block_repeated"] = (
            names[(row["district_raw"], row["block_raw"], row["candidate_name"])] > 1
        )
    return kept, exclusions, duplicates


def write_outputs(raw, out):
    files = sorted(raw.glob("winners/*/*GPM.pdf"))
    if not files:
        raise ValueError(f"No Mukhiya reports under {raw}")
    records, issues, coverage = [], [], []
    sources = {}
    for file in files:
        relative = str(file.relative_to(raw))
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        sources[relative] = digest
        decode_issues = []
        rows = pdf_winners(raw, "winners", relative, decode_issues)
        for issue in decode_issues:
            issues.append(
                {
                    "source_file": relative,
                    "source_serial": issue["source_serial"],
                    "source_page": issue["source_page"],
                    "field": FIELDS[issue["column"]],
                    "kind": "unresolved_glyph_order",
                    "detail": issue["reason"],
                    "source_box": issue["source_box"],
                }
            )
        issue_counts = collections.Counter(x["source_serial"] for x in decode_issues)
        seats = collections.Counter(
            (r["block_raw"], r["panchayat_raw"])
            for r in rows
            if r["block_raw"] and r["panchayat_raw"]
        )
        names = collections.Counter(
            (r["block_raw"], r["candidate_name"])
            for r in rows
            if r["block_raw"] and r["candidate_name"]
        )
        first_record = {}
        for row in rows:
            serial = row.pop("serial")
            row.update(
                record_id=f"{file.parent.name}_mukhiya_{serial:04}",
                collection_year=2011,
                election_year=YEAR_ASSIGNMENT["election_year"],
                year_basis=YEAR_ASSIGNMENT["year_basis"],
                district_raw=file.parent.name,
                office="mukhiya",
                outcome="winner",
                source_serial=serial,
                source_sha256=digest,
                decode_issue_count=issue_counts[serial],
                missing_block=not row["block_raw"],
                seat_label_repeated=(
                    seats[(row["block_raw"], row["panchayat_raw"])] > 1
                    if row["block_raw"] and row["panchayat_raw"]
                    else None
                ),
                name_within_block_repeated=(
                    names[(row["block_raw"], row["candidate_name"])] > 1
                    if row["block_raw"] and row["candidate_name"]
                    else None
                ),
                gender=GENDERS.get(row["gender_raw"]),
            )
            row["reservation_category"], row["reservation_women"] = reservation(
                row["reservation_raw"]
            )
            content_key = (row["block_raw"], *(row[field] for field in FIELDS[1:]))
            row["duplicate_of_record_id"] = None
            if not row["decode_issue_count"]:
                row["duplicate_of_record_id"] = first_record.get(content_key)
                first_record.setdefault(content_key, row["record_id"])
            for field in NUMBERS:
                value = row[field + "_raw"]
                row[field] = int(value) if value and value.isdecimal() else None
                if (
                    field == "age"
                    and row[field] is not None
                    and not 18 <= row[field] <= 120
                ):
                    row[field] = None
                if value and row[field] is None:
                    issues.append(
                        {
                            "source_file": relative,
                            "source_serial": serial,
                            "source_page": row["source_page"],
                            "field": field,
                            "kind": "invalid_numeric",
                            "detail": value,
                            "source_box": row["source_box"],
                        }
                    )
            records.append(row)
        coverage.append(
            {
                "district_raw": file.parent.name,
                "source_file": relative,
                "pages": max(r["source_page"] for r in rows),
                "winner_records": len(rows),
                "reservation_labels_present": sum(
                    bool(r["reservation_raw"]) for r in rows
                ),
                "reservation_category_mapped": sum(
                    r["reservation_category"] is not None for r in rows
                ),
                "women_reservation_mapped": sum(
                    r["reservation_women"] is not None for r in rows
                ),
                "missing_block_records": sum(r["missing_block"] for r in rows),
                "rows_with_repeated_seat_labels": sum(
                    bool(r["seat_label_repeated"]) for r in rows
                ),
                "decode_issue_cells": len(decode_issues),
                "duplicate_content_records": sum(
                    r["duplicate_of_record_id"] is not None for r in rows
                ),
            }
        )
        print(file.parent.name, len(rows), flush=True)
    source_record_count = len(records)
    records, exclusions, duplicate_count = release_records(records)
    issues.extend(exclusions)
    schema = pa.schema(
        [
            (
                name,
                pa.int64()
                if name in INTS
                else pa.bool_()
                if name in BOOLS
                else pa.string(),
            )
            for name in records[0]
        ]
    )
    out.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(records, schema=schema),
        out / "winner_records.parquet",
        compression="zstd",
    )
    write_csv(out / "coverage.csv", coverage, list(coverage[0]))
    write_csv(
        out / "issues.csv",
        issues,
        [
            "source_file",
            "source_serial",
            "source_page",
            "field",
            "kind",
            "detail",
            "source_box",
        ],
    )
    labels = collections.Counter(r["reservation_raw"] for r in records)
    label_rows = [
        {
            "reservation_raw": label,
            "records": count,
            "reservation_category": reservation(label)[0],
            "reservation_women": reservation(label)[1],
        }
        for label, count in sorted(
            labels.items(), key=lambda item: (-item[1], item[0] or "")
        )
    ]
    write_csv(out / "reservation_labels.csv", label_rows, list(label_rows[0]))
    validation = {
        "source_records": source_record_count,
        "excluded_missing_location_or_name": len(exclusions),
        "excluded_exact_repeats": duplicate_count,
        "districts": len(files),
        "pages": sum(r["pages"] for r in coverage),
        "winner_records": len(records),
        "election_year": YEAR_ASSIGNMENT["election_year"],
        "year_basis": YEAR_ASSIGNMENT["year_basis"],
        "source_serials": "Consecutive from 1 within each PDF; checked before output",
        "record_ids_unique": len({r["record_id"] for r in records}) == len(records),
        "missing_block_records": sum(r["missing_block"] for r in records),
        "decode_issue_cells": sum(r["decode_issue_count"] for r in records),
        "duplicate_content_records": sum(
            r["duplicate_of_record_id"] is not None for r in records
        ),
        "reservation_labels_present": sum(bool(r["reservation_raw"]) for r in records),
        "reservation_category_mapped": sum(
            r["reservation_category"] is not None for r in records
        ),
        "women_reservation_mapped": sum(
            r["reservation_women"] is not None for r in records
        ),
        "rows_with_repeated_seat_labels": sum(
            bool(r["seat_label_repeated"]) for r in records
        ),
        "scope": (
            "Source winner records, not all candidates, unique seats or "
            "statewide completeness"
        ),
        "overlap": (
            "Includes the same 338 primary Gaya PDF records as the pilot; do "
            "not add the two counts"
        ),
    }
    metadata = {
        "validation": validation,
        "year_assignment": {
            "path": "data/PROVENANCE.json",
            "election_year": YEAR_ASSIGNMENT["election_year"],
            "basis": YEAR_ASSIGNMENT["year_basis"],
            "sha256": hashlib.sha256(YEAR_RECEIPT.read_bytes()).hexdigest(),
        },
        "sources": sources,
        "source_root": "data/2011/raw/reports",
        "code_sha256": {
            name: hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in [
                "parse_reports.py",
                "parse_gaya.py",
                "hindi.py",
                "font_map.json",
            ]
        },
        "columns": {
            f.name: {
                "type": str(f.type),
                "nullable": f.nullable,
                "description": DESCRIPTIONS[f.name],
            }
            for f in schema
        },
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.iterdir())
            if p.is_file() and p.name not in {"MANIFEST.json", "README.md"}
        },
    }
    (out / "MANIFEST.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(validation))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=Path("data/2011/mukhiya_reports"))
    args = parser.parse_args()
    write_outputs(args.raw, args.out)

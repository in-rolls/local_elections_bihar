"""Check saved mukhiya reservations against 2021 totals and candidate records."""

import argparse
import base64
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from bs4 import BeautifulSoup
from release_2021 import KEY, SEAT, key, sha, table

RAW = Path("data/raw/reservation_check_2021")
OUT = Path("data/fin/reservation_check_2021")
INPUTS = {
    "reservations": Path("data/fin/portal_2021_2026/reservations.parquet"),
    "current_winners": Path("data/fin/portal_2021_2026/winners.parquet"),
    "candidates": Path("data/release/2021/gp_head_candidates_2021.parquet"),
    "winners": Path("data/release/2021/gp_head_winner_records_2021.parquet"),
}
CATEGORIES = {
    f"{caste} ({gender})": (code, gender == "महिला")
    for caste, code in [
        ("अनारक्षित", "open"),
        ("पिछड़ा वर्ग", "bc"),
        ("अनुसूचित जाति", "sc"),
        ("अनुसूचित जन - जाति", "st"),
    ]
    for gender in ["महिला", "अन्य"]
}


def category(value):
    normalized = " ".join(value.split())
    if normalized not in CATEGORIES:
        raise ValueError(f"Unknown seat reservation: {value!r}")
    return CATEGORIES[normalized]


def unique(rows, fields):
    indexed = {key(r, fields): r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError("Duplicate source key")
    return indexed


def report_totals(body):
    soup = BeautifulSoup(body, "html.parser")
    if "पंचायत आम निर्वाचन, 2021" not in soup.get_text(" ", strip=True):
        raise ValueError("Missing explicit 2021 report heading")
    matches = []
    for row in soup.select("table tr"):
        cells = [
            c.get_text(" ", strip=True)
            for c in row.find_all(["td", "th"], recursive=False)
        ]
        if cells and "ग्राम पंचायत मुखिया" in cells[0]:
            matches.append(cells)
    if len(matches) != 1 or len(matches[0]) != 6:
        raise ValueError("Expected one mukhiya reservation-total row")
    return dict(
        zip(["total", "sc", "st", "bc", "women"], map(int, matches[0][1:]), strict=True)
    )


def audit(reservations, candidates, winners, current_winners, official):
    seats = unique(reservations, SEAT)
    unique(candidates, KEY)
    unique(winners, SEAT)
    current = unique(current_winners, SEAT)
    if any(r["year"] != 2021 for r in candidates + winners):
        raise ValueError("Candidate/winner records must be explicitly dated 2021")
    if any(r["post_id"] != 3 for r in reservations + candidates + winners):
        raise ValueError("Expected mukhiya records only")
    codes = {k: category(r["seat_reservation"]) for k, r in seats.items()}
    totals = {"total": len(seats), "sc": 0, "st": 0, "bc": 0, "women": 0}
    for caste, female in codes.values():
        if caste in totals:
            totals[caste] += 1
        totals["women"] += int(female)
    checks = {
        "official_2021_totals": official,
        "current_portal_totals": totals,
        "current_minus_official": {k: totals[k] - official[k] for k in totals},
        "reservation_rows_with_explicit_year": sum(
            r["year"] is not None for r in reservations
        ),
        "districts": len({k[0] for k in seats}),
        "blocks": len({k[:2] for k in seats}),
    }
    common = seats.keys() & current.keys()
    reservation_agreement = collections.Counter()
    for k in common:
        value = current[k]["reservation_for_reported"]
        if value is None:
            reservation_agreement["unknown"] += 1
        elif value.strip() not in {"महिला", "अन्य"}:
            raise ValueError(f"Unknown winner-feed seat reservation: {value!r}")
        else:
            agrees = (value.strip() == "महिला") == codes[k][1]
            reservation_agreement["agrees" if agrees else "disagrees"] += 1
    checks["current_feeds_women_reservation"] = {
        "matched_seats": len(common),
        "missing_winner_feed_seats": len(seats.keys() - current.keys()),
        "missing_reservation_feed_seats": len(current.keys() - seats.keys()),
        **{n: reservation_agreement[n] for n in ["agrees", "disagrees", "unknown"]},
    }
    flagged = []
    for kind, rows in [("candidates", candidates), ("winners", winners)]:
        missing = sum(key(r, SEAT) not in seats for r in rows)
        if missing:
            raise ValueError(f"{kind}: {missing} records lack a reservation key")
        female = [r for r in rows if codes[key(r, SEAT)][1]]
        checks[kind] = {
            "records": len(rows),
            "unmatched_reservation_keys": missing,
            "records_in_women_reserved_seats": len(female),
            "reported_gender_in_women_reserved_seats": dict(
                sorted(
                    collections.Counter(
                        r["candidate_gender"].strip() for r in female
                    ).items()
                )
            ),
        }
        if kind != "winners":
            continue
        for r in female:
            if r["candidate_gender"].strip() == "महिला":
                continue
            k = key(r, SEAT)
            other = current.get(k)
            flagged.append(
                {
                    **{f: r[f] for f in KEY},
                    "seat_reservation": seats[k]["seat_reservation"],
                    "gender_2021": r["candidate_gender"],
                    "gender_current": other["candidate_gender"] if other else None,
                    "same_reported_name": (
                        r["candidate_name"].strip() == other["candidate_name"].strip()
                        if other
                        else None
                    ),
                    "candidate_document_url": r["affidavit_url"],
                    "current_document_url": other["affidavit_url"] if other else None,
                    "same_document_url": (
                        r["affidavit_url"] == other["affidavit_url"]
                        if other and r["affidavit_url"] and other["affidavit_url"]
                        else None
                    ),
                    "reservation_source_sha256": seats[k]["source_sha256"],
                    "candidate_source_sha256": r["source_sha256"],
                    "current_winner_source_sha256": other["source_sha256"]
                    if other
                    else None,
                }
            )
    checks["flagged_winners"] = len(flagged)
    checks["flagged_winners_current_gender"] = dict(
        sorted(
            collections.Counter(
                r["gender_current"] or "missing" for r in flagged
            ).items()
        )
    )
    checks["flagged_winners_same_reported_name"] = sum(
        r["same_reported_name"] is True for r in flagged
    )
    checks["flagged_winners_same_document_url"] = sum(
        r["same_document_url"] is True for r in flagged
    )
    checks["interpretation"] = (
        "Matching totals do not validate individual 2021 assignments. Gender "
        "disagreements flag source conflicts, not proven reservation violations. "
        "No reservation or gender values are corrected or promoted by this check."
    )
    return checks, flagged


def build(out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    receipt = RAW / "report_ch1.jsonl.gz"
    with gzip.open(receipt, "rt") as stream:
        event = json.loads(stream.read())
    body = base64.b64decode(event["body_base64"])
    if event["status"] != 200 or hashlib.sha256(body).hexdigest() != event["sha256"]:
        raise ValueError("Invalid report receipt")
    checks, flagged = audit(
        **{name: pq.read_table(path).to_pylist() for name, path in INPUTS.items()},
        official=report_totals(body),
    )
    fields = [(f, pa.int64()) for f in KEY] + [
        ("seat_reservation", pa.string()),
        ("gender_2021", pa.string()),
        ("gender_current", pa.string()),
        ("same_reported_name", pa.bool_()),
        ("candidate_document_url", pa.string()),
        ("current_document_url", pa.string()),
        ("same_document_url", pa.bool_()),
        ("reservation_source_sha256", pa.string()),
        ("candidate_source_sha256", pa.string()),
        ("current_winner_source_sha256", pa.string()),
    ]
    info = table(out, "flagged_winners", flagged, fields)
    (out / "validation.json").write_text(
        json.dumps(checks, indent=2, ensure_ascii=False) + "\n"
    )
    manifest = {
        "purpose": "Source reconciliation only; not a 2021 treatment release",
        "key": KEY,
        "inputs": {str(p): sha(p) for p in INPUTS.values()},
        "receipts": {str(p): sha(p) for p in sorted(RAW.glob("*.jsonl.gz"))},
        "report_url": event["url"],
        "parser_sha256": sha(Path(__file__)),
        "files": [info],
        "fields": {
            **dict.fromkeys(KEY, "Original composite 2021 candidate key component"),
            "seat_reservation": "Unmodified current reservation-feed label",
            "gender_2021": "Unmodified explicitly 2021 candidate-feed gender",
            "gender_current": ("Current winner-feed gender; null if no seat match"),
            "candidate_document_url": "Document URL in dated 2021 candidate feed",
            "current_document_url": "Document URL in current winner feed",
            "same_document_url": (
                "Exact equality of nonempty document URLs; null if missing. "
                "Does not establish the correct gender or reservation label."
            ),
            "same_reported_name": (
                "Literal name equality after edge whitespace trim; "
                "not an identity match"
            ),
            **{
                f: "Respective response-body hash retained in input provenance"
                for f, _ in fields
                if f.endswith("_source_sha256")
            },
        },
    }
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    (out / "SCHEMA.json").write_text(json.dumps(info["schema"], indent=2) + "\n")
    with (out / "dictionary.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["column", "type", "description"])
        for name, dtype in fields:
            writer.writerow([name, str(dtype), manifest["fields"][name]])
    files = [
        out / n
        for n in [
            "flagged_winners.parquet",
            "validation.json",
            "MANIFEST.json",
            "SCHEMA.json",
            "dictionary.csv",
        ]
    ]
    (out / "CHECKSUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in files))
    print(json.dumps(checks, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    build(parser.parse_args().out)

"""Parse Gaya workbook winners and link runner-up seats to the winner PDF."""

import argparse
import collections
import csv
import hashlib
import json
from itertools import pairwise
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import xlrd

from local_elections_bihar.year2011.hindi import cell_text, decoded_pdf, kruti_text

ROOT = Path("data/2011/raw/reports")
YEAR_RECEIPT = Path(__file__).resolve().parents[3] / "data/PROVENANCE.json"
YEAR_ASSIGNMENT = {
    "election_year": 2011,
    "year_basis": (
        "Maintainer-confirmed 2011; prior-election columns refer to "
        "2001/2006; historical 2011 collection"
    ),
}
SOURCES = {
    "winners": "winners/GAYA/GAYA_GPM.pdf",
    "spreadsheet": "mukhiya_spreadsheets/Gaya.xls",
    "runners": "runners/GAYA/GAYA_gpm.pdf",
}
FIELDS = [
    "serial",
    "panchayat_raw",
    "candidate_name",
    "relative_name",
    "address_raw",
    "reservation_raw",
    "gender_raw",
    "age_raw",
    "category_raw",
    "phone_raw",
    "occupation_raw",
    "annual_income_raw",
    "sons_raw",
    "daughters_raw",
    "previous_office_2001_raw",
    "previous_office_2006_raw",
    "education_raw",
]
BLOCKS = {
    "Amas": "आमस",
    "atree": "अतरी",
    "Banke Bajar": "बांकेबाजार",
    "Barachatti": "बाराचट्टी",
    "Belaganj": "बेलागंज",
    "Bodhgaya": "बोधगया",
    "Dobhi": "डोभी",
    "Dumariya": "डुमरिया",
    "Emamganj": "इमामगंज",
    "FATEHPUR": "फतेहपुर",
    "guraru": "गुरारू",
    "GURUAA": "गुरूआ",
    "Khizarsarai": "खिजरसराय",
    "KONCH": "कोंच",
    "MANPUR": "मानपुर",
    "mohanpur": "मोहनपुर",
    "MOHARAA": "मोहड़ा",
    "NAGAR": "नगर",
    "Nimchak Bathani": "नीमचक बथानी",
    "Paraiya": "परैया",
    "Sherghati": "शेरघाटी",
    "Tankuppa": "टनकुप्पा",
    "Tikari": "टिकारी",
    "Vajirganj": "वजीरगंज",
    "Wazirganj": "वजीरगंज",
}


def latin_text(page, box):
    return "".join(
        c["text"]
        for c in page.chars
        if c["fontname"].endswith("+Arial-Bold")
        and box[0] <= c["x0"] < box[2]
        and box[1] <= c["top"] < box[3]
    ).strip()


def grid_rows(page, table, ncols, column_edges=None, decode_issues=None):
    """Use header column boundaries even when final-row rules are truncated."""
    xs = sorted(
        {round(b[i], 1) for r in table.rows[:2] for b in r.cells if b for i in [0, 2]}
    )
    if column_edges is not None:
        xs = column_edges
    if len(xs) != ncols + 1:
        raise ValueError(f"Expected {ncols} columns on page {page.page_number}: {xs}")
    ys = sorted(
        {
            round(e["top"], 1)
            for e in page.edges
            if e["orientation"] == "h"
            and e["width"] > 50
            and table.bbox[1] <= e["top"] <= table.bbox[3] + 1
        }
    )
    anchors = collections.defaultdict(list)
    for c in page.chars:
        if xs[0] <= (c["x0"] + c["x1"]) / 2 < xs[1] and c["text"].isdigit():
            if table.bbox[1] < c["top"] < table.bbox[3]:
                anchors[round(c["top"], 1)].append(c)
    for top, chars in sorted(anchors.items()):
        serial = "".join(c["text"] for c in sorted(chars, key=lambda c: c["x0"]))
        bottom = max(c["bottom"] for c in chars)
        lower = max(y for y in ys if y <= top)
        upper = min(y for y in ys if y >= bottom)
        cells = []
        for column, (a, b) in enumerate(pairwise(xs)):
            box = (a, lower, b, upper)
            try:
                cells.append(cell_text(page, box))
            except ValueError as error:
                if decode_issues is None:
                    raise
                decode_issues.append(
                    {
                        "source_serial": int(serial),
                        "source_page": page.page_number,
                        "column": column,
                        "source_box": json.dumps(box),
                        "reason": str(error),
                    }
                )
                cells.append(None)
        if cells[0] != serial:
            raise ValueError(f"Serial cell crosses a boundary: {cells}")
        yield int(serial), cells, [xs[0], lower, xs[-1], upper]


def pdf_winners(root, kind, source_file=None, decode_issues=None):
    records = []
    source_file = source_file or SOURCES[kind]
    path = root / source_file
    with decoded_pdf(path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            if len(tables) != 1:
                raise ValueError(f"Unexpected tables on {path}:{page.page_number}")
            block_raw = latin_text(page, (400, 60, 550, 85))
            if path.parent.name == "GAYA" and block_raw not in BLOCKS:
                raise ValueError(f"Unknown or missing block: {block_raw!r}")
            heading = cell_text(page, (0, 0, page.width, 110))
            if "ग्राम पंचायत मुखिया" not in heading:
                raise ValueError(
                    f"Unrecognized office heading: {path}:{page.page_number}"
                )
            cols = 17 if kind == "winners" else 16
            for serial, cells, box in grid_rows(
                page, tables[0], cols, decode_issues=decode_issues
            ):
                if kind == "alternate":
                    cells.insert(1, None)
                records.append(
                    {
                        **dict(zip(FIELDS, cells, strict=True)),
                        "serial": serial,
                        "block_raw": block_raw,
                        "block": BLOCKS[block_raw]
                        if path.parent.name == "GAYA"
                        else None,
                        "source_file": source_file,
                        "source_page": page.page_number,
                        "source_box": json.dumps(box),
                    }
                )
    serials = [r["serial"] for r in records]
    if serials != list(range(1, max(serials) + 1)):
        raise ValueError(f"Missing or repeated source serials: {path}")
    return records


def spreadsheet(root):
    book = xlrd.open_workbook(root / SOURCES["spreadsheet"], formatting_info=True)
    sheet = book.sheet_by_index(0)
    if "2011" not in str(sheet.cell_value(0, 0)):
        raise ValueError("Workbook no longer has the explicit 2011 heading")
    records, block = [], None
    for i in range(sheet.nrows):
        values = []
        for j in range(12):
            value = sheet.cell_value(i, j)
            font = book.font_list[book.xf_list[sheet.cell_xf_index(i, j)].font_index]
            values.append(
                kruti_text(value)
                if isinstance(value, str) and font.name == "Kruti Dev 010"
                else value
            )
        if i == 1:
            block = values[9]
        elif isinstance(values[0], str) and values[0].startswith("प्रखण्ड:"):
            block = values[0].split(":", 1)[1].strip()
        if isinstance(values[0], (int, float)):
            records.append(
                dict(
                    zip(
                        [
                            "serial",
                            "panchayat_raw",
                            "candidate_name",
                            "age_raw",
                            "address_raw",
                            "education_raw",
                            "economic_class_raw",
                            "category_raw",
                            "annual_income_raw",
                            "occupation_raw",
                            "sons_raw",
                            "daughters_raw",
                        ],
                        values,
                        strict=True,
                    )
                )
                | {
                    "block": block,
                    "source_row": i + 1,
                    "source_file": SOURCES["spreadsheet"],
                }
            )
    return records


def runner_names(root):
    records, block = [], None
    pending_heading = None
    with decoded_pdf(root / SOURCES["runners"]) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            xs = sorted(
                {
                    round(b[i], 1)
                    for r in tables[0].rows[:2]
                    for b in r.cells
                    if b
                    for i in [0, 2]
                }
            )
            headers = [
                c
                for c in page.chars
                if c["fontname"].endswith("+Arial-Bold") and c["top"] > 110
            ]
            heading_names = {
                round(c["top"], 1): cell_text(
                    page, (675, c["top"] - 1, page.width, c["top"] + 15)
                )
                for c in headers
            }
            used_headers = set()
            for table in tables:
                for serial, cells, box in grid_rows(page, table, 16, xs):
                    previous = [c for c in headers if c["top"] < box[1]]
                    if previous:
                        top = max(c["top"] for c in previous)
                        block = "".join(
                            c["text"] for c in previous if abs(c["top"] - top) < 1
                        )
                    heading = (
                        heading_names[round(top, 1)]
                        if previous and round(top, 1) not in used_headers
                        else pending_heading
                        if not previous
                        else None
                    )
                    pending_heading = None
                    if previous:
                        used_headers.add(round(top, 1))
                    if block not in BLOCKS:
                        raise ValueError(f"Unknown runner block: {block!r}")
                    records.append(
                        {
                            "source_serial": serial,
                            "block_raw": block,
                            "block": BLOCKS[block],
                            "candidate_name": cells[1],
                            "reservation_raw": cells[4],
                            "block_first_panchayat_heading": heading,
                            "source_page": page.page_number,
                            "source_file": SOURCES["runners"],
                        }
                    )
            if headers:
                top = max(c["top"] for c in headers)
                block = "".join(c["text"] for c in headers if abs(c["top"] - top) < 1)
                pending_heading = (
                    heading_names[round(top, 1)]
                    if round(top, 1) not in used_headers
                    else None
                )
    if [r["source_serial"] for r in records] != list(range(1, len(records) + 1)):
        raise ValueError("Runner source serials are not consecutive")
    return records


def link_runner_seats(runners, winners):
    """Infer GP labels from the paired reports, requiring complete alignment."""
    by_serial = {r["serial"]: r for r in winners}
    serials = [r["source_serial"] for r in runners]
    if (
        len(by_serial) != len(winners)
        or len(set(serials)) != len(serials)
        or set(serials) != set(by_serial)
    ):
        raise ValueError("Runner/winner serials must have a complete one-to-one match")
    heads = 0
    linked = []
    for runner in runners:
        winner = by_serial[runner["source_serial"]]
        if any(runner[key] != winner[key] for key in ["block_raw", "reservation_raw"]):
            raise ValueError("Runner/winner block or reservation alignment changed")
        heading = runner["block_first_panchayat_heading"]
        if heading is not None:
            if not heading or heading != winner["panchayat_raw"]:
                raise ValueError("Runner GP heading disagrees with companion winner")
            heads += 1
        if not winner["panchayat_raw"]:
            raise ValueError("Companion winner has no GP label")
        linked.append(
            {
                **runner,
                "panchayat_raw": winner["panchayat_raw"],
                "seat_link_basis": "inferred_paired_report_order",
                "seat_source_file": winner["source_file"],
                "seat_source_page": winner["source_page"],
                "seat_source_record_id": f"GAYA_mukhiya_{winner['serial']:04}",
            }
        )
    if heads != len({r["block_raw"] for r in runners}):
        raise ValueError("Expected one corroborating GP heading per printed block")
    return linked, {
        "basis": "inferred_paired_report_order",
        "aligned_source_rows": len(linked),
        "corroborating_gp_headings": heads,
        "checks": (
            "Complete unique serials; exact block and reservation text; GP headings"
        ),
        "limitation": (
            "GP inferred from companion report, not individually printed for runners; "
            "serial is not an official seat identifier"
        ),
    }


def minimum_records(records):
    kept, excluded = [], []
    for record in records:
        missing = [
            field
            for field in ["district", "block", "panchayat_raw", "candidate_name"]
            if not (record.get(field) or "").strip()
        ]
        if missing:
            excluded.append({"record_id": record["record_id"], "missing": missing})
        else:
            kept.append(record)
    return kept, excluded


def write_csv(path, rows, columns):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


DESCRIPTIONS = {
    "record_id": "Source-record identifier; not a verified person or seat identifier",
    "election_year": (
        "2011; see year_basis for workbook date or PDF collection confirmation"
    ),
    "collection_year": (
        "Year of historical handoff folder; not independently verified election year"
    ),
    "year_basis": (
        "Evidence for the year assignment or reason for leaving it unresolved"
    ),
    "district": "Gaya, as printed in the source",
    "office": "mukhiya, identified by the printed office heading",
    "outcome": (
        "Outcome asserted by this source; contradictory sources remain separate"
    ),
    "serial": "Serial printed in the workbook, retained as a string",
    "source_serial": "Printed PDF serial; consecutive within the report",
    "source_file": "Path relative to data/2011/raw/reports",
    "source_sha256": "SHA-256 of original source document",
    "source_page": "Original PDF page, one-based",
    "source_row": "Original Sheet1 row, one-based",
    "source_box": "JSON [left, top, right, bottom] in PDF points, top-origin",
    "block_raw": "English block label as printed; capitalization retained",
    "block": "Hindi block label; PDF labels mapped explicitly to workbook block names",
    "panchayat_raw": (
        "GP label from this source or the linked companion winner PDF; "
        "runner links are identified by seat_link_basis"
    ),
    "block_first_panchayat_heading": (
        "GP printed at the block heading, attached only to its first row for "
        "alignment checking; null on other rows, not a group-wide GP assignment"
    ),
    "seat_link_basis": (
        "inferred_paired_report_order: complete serial, block and exact reservation "
        "alignment with winner PDF, corroborated by block-first GP headings"
    ),
    "seat_source_file": "Companion PDF supplying the GP; relative to raw/reports",
    "seat_source_page": "One-based page supplying the GP in the companion PDF",
    "seat_source_record_id": "Row in mukhiya_reports/winner_records supplying the GP",
    "seat_source_sha256": "SHA-256 of the companion PDF supplying the GP",
    "candidate_name": "Decoded candidate name, preserving spelling and honorifics",
    "relative_name": "Printed father/husband name; relationship not distinguished",
    "address_raw": (
        "Decoded address as reported, possibly including phone numbers in workbook"
    ),
    "phone_raw": "Printed phone cell; malformed numbers retained as text",
    "reservation_raw": "Reported seat reservation; distinct from candidate category",
    "category_raw": "Reported candidate social category, not seat reservation",
    "economic_class_raw": "Workbook economic-class label, separate from caste/category",
    "education_raw": "Reported qualification; no degree threshold imputed",
    "occupation_raw": "Reported occupation, including malformed overflow text",
    "gender_raw": "Source gender spelling, even where it conflicts with another source",
    "gender": "female/male from reviewed Hindi source labels; no inference from names",
    "reservation_women": (
        "True when reservation cell explicitly contains महिला; otherwise unknown"
    ),
    "previous_office_2001_raw": (
        "Source claim about elected office in 2001; blank is not coded no"
    ),
    "previous_office_2006_raw": (
        "Source claim about elected office in 2006; blank is not coded no"
    ),
    "spreadsheet_match": (
        "Exact normalized name within block: unique, unmatched or "
        "ambiguous; not a seat join"
    ),
    "spreadsheet_row": (
        "Workbook row for a unique name/block comparison; null otherwise"
    ),
    "alternate_matches": (
        "Same source serial, block and candidate name in alternate winner PDF"
    ),
    "seat_label_repeated": (
        "Another PDF record has the same block and literal panchayat label"
    ),
    "name_within_block_repeated": (
        "Another PDF record has the same name within the block"
    ),
    "age": "Reported age in years; values outside 18-120 left null",
    "annual_income": (
        "Reported annual income; currency not explicit in the printed heading"
    ),
    "sons": "Reported number of sons; zero retained",
    "daughters": "Reported number of daughters; zero retained",
}
for _field in ["age", "annual_income", "sons", "daughters"]:
    DESCRIPTIONS[_field + "_raw"] = "Unrecoded source cell for " + _field


def metadata(out):
    columns = {}
    for name in [
        "spreadsheet_winner_records",
        "runner_up_records",
    ]:
        table = pq.read_table(out / f"{name}.parquet")
        columns[f"{name}.parquet"] = {
            field.name: {
                "type": str(field.type),
                "nullable": field.nullable,
                "description": DESCRIPTIONS[field.name],
                "null_count": table[field.name].null_count,
                "empty_string_count": sum(
                    value == "" for value in table[field.name].to_pylist()
                ),
                "missing": (
                    "Null for unavailable typed values; empty text preserves "
                    "blank source cell"
                ),
            }
            for field in table.schema
        }
    return columns


def run(root, out):
    winners = pdf_winners(root, "winners")
    excel = spreadsheet(root)
    runners, seat_linkage = link_runner_seats(runner_names(root), winners)
    source_hashes = {
        path: hashlib.sha256((root / path).read_bytes()).hexdigest()
        for path in SOURCES.values()
    }
    for r in runners:
        r.update(
            record_id=f"gaya_runner_{r['source_serial']:03}",
            collection_year=2011,
            election_year=YEAR_ASSIGNMENT["election_year"],
            year_basis=YEAR_ASSIGNMENT["year_basis"],
            district="Gaya",
            office="mukhiya",
            outcome="runner_up",
            source_sha256=source_hashes[r["source_file"]],
            seat_source_sha256=source_hashes[r["seat_source_file"]],
        )
    out.mkdir(parents=True, exist_ok=True)
    issues = []
    excel_rows = []
    for r in excel:
        record = {
            k: v
            if k == "source_row"
            else str(int(v))
            if isinstance(v, float) and v.is_integer()
            else str(v)
            for k, v in r.items()
        }
        record.update(
            election_year=2011,
            source_sha256=source_hashes[r["source_file"]],
            year_basis="Explicit workbook heading",
            district="Gaya",
            office="mukhiya",
            outcome="winner",
            record_id=f"gaya_xls_row_{r['source_row']:03}",
        )
        for field in ["age", "annual_income", "sons", "daughters"]:
            value = record[field + "_raw"]
            record[field] = int(value) if value.isdigit() else None
            if value and record[field] is None:
                issues.append(
                    {
                        "record_id": record["record_id"],
                        "kind": "non_numeric",
                        "field": field,
                        "primary": value,
                        "comparison": "",
                        "source": r["source_file"],
                    }
                )
        if record["age"] is not None and not 18 <= record["age"] <= 120:
            issues.append(
                {
                    "record_id": record["record_id"],
                    "kind": "age_out_of_range",
                    "field": "age",
                    "primary": record["age_raw"],
                    "comparison": "",
                    "source": r["source_file"],
                }
            )
            record["age"] = None
        excel_rows.append(record)
    excel_rows, excluded_excel = minimum_records(excel_rows)
    excel_schema = pa.schema(
        [
            (
                k,
                pa.int64()
                if k
                in {
                    "source_row",
                    "election_year",
                    "age",
                    "annual_income",
                    "sons",
                    "daughters",
                }
                else pa.string(),
            )
            for k in excel_rows[0]
        ]
    )
    pq.write_table(
        pa.Table.from_pylist(excel_rows, schema=excel_schema),
        out / "spreadsheet_winner_records.parquet",
        compression="zstd",
    )
    published_runners, excluded_runners = minimum_records(runners)
    pq.write_table(
        pa.Table.from_pylist(
            published_runners,
            schema=pa.schema(
                [
                    (
                        k,
                        pa.int64()
                        if k
                        in {
                            "source_serial",
                            "source_page",
                            "seat_source_page",
                            "collection_year",
                            "election_year",
                        }
                        else pa.string(),
                    )
                    for k in runners[0]
                ]
            ),
        ),
        out / "runner_up_records.parquet",
        compression="zstd",
    )
    write_csv(
        out / "issues.csv",
        issues,
        ["record_id", "kind", "field", "primary", "comparison", "source"],
    )
    report = {
        "spreadsheet_rows": len(excel),
        "runner_name_rows": len(runners),
        "published_spreadsheet_winners": len(excel_rows),
        "published_runners": len(published_runners),
        "excluded_records": excluded_excel + excluded_runners,
        "runner_seat_linkage": seat_linkage,
        "year_assignment": YEAR_ASSIGNMENT["year_basis"],
        "review_needed": "Extracted PDF/workbook names and outcomes need review",
        "issues_by_kind": dict(collections.Counter(r["kind"] for r in issues)),
        "scope": "Gaya workbook winners and runner-up list; overlapping source claims",
    }
    manifest = {
        "columns": metadata(out),
        "validation": report,
        "year_assignment": {
            "path": "data/PROVENANCE.json",
            "election_year": YEAR_ASSIGNMENT["election_year"],
            "basis": YEAR_ASSIGNMENT["year_basis"],
            "sha256": hashlib.sha256(YEAR_RECEIPT.read_bytes()).hexdigest(),
        },
        "sources": {
            k: {
                "path": "data/2011/raw/reports/" + v,
                "sha256": hashlib.sha256((root / v).read_bytes()).hexdigest(),
            }
            for k, v in SOURCES.items()
        },
        "code_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                Path(__file__).with_name("hindi.py"),
                Path(__file__).with_name("font_map.json"),
                Path(__file__).with_name("kruti_dev_010.json"),
                Path("tests/fixtures/2011/gaya_visual_review.csv"),
                Path("uv.lock"),
            ]
        },
        "files": {
            p.name: {
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in [
                out / name
                for name in (
                    "spreadsheet_winner_records.parquet",
                    "runner_up_records.parquet",
                    "issues.csv",
                )
            ]
        },
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=Path("data/2011/gaya_mukhiya"))
    args = parser.parse_args()
    run(args.raw, args.out)

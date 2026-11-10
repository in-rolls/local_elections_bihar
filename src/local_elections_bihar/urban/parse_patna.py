"""Build typed Patna municipal data offline from saved official and TCPD sources."""

import argparse
import csv
import hashlib
import json
import unicodedata
from collections import Counter
from functools import cache
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from bs4 import BeautifulSoup

RAW = Path("data/raw/urban/patna")
REFERENCE = Path("data/reference/urban/patna")
RELEASE = Path("data/release/urban/patna")
TCPD = Path("../local_elections/data/reference/tcpd/tcpd_casi_ulb_v1.1.csv")
TCPD_SHA = "e158240acb5cab355f513c70aa3732cc4198705c0acdd957ee5670834a39a851"
SEX = {"महिला": "female", "पुरुष": "male", "Female": "female", "Male": "male"}
CATEGORY = {"अनारक्षित": "General", "पिछड़ा वर्ग": "BC", "अनुसूचित जाति": "SC"}
SCHEMA = pa.schema(
    [
        ("election_year", pa.int16()),
        ("city", pa.string()),
        ("office", pa.string()),
        ("ward_id", pa.string()),
        ("ward_id_source", pa.string()),
        ("candidate_name", pa.string()),
        ("relative_name", pa.string()),
        ("sex_recorded", pa.string()),
        ("is_woman", pa.bool_()),
        ("age_reported", pa.int16()),
        ("age_reference", pa.string()),
        ("education_reported", pa.string()),
        ("candidate_category", pa.string()),
        ("votes", pa.int32()),
        ("position", pa.int16()),
        ("is_winner", pa.bool_()),
        ("reservation_category", pa.string()),
        ("is_women_reserved", pa.bool_()),
        ("sex_reservation_conflict", pa.bool_()),
        ("reservation_source_raw", pa.string()),
        ("reservation_basis", pa.string()),
        ("source_kind", pa.string()),
        ("source_file", pa.string()),
        ("source_sha256", pa.string()),
        ("source_row", pa.int32()),
        ("polling_date_reported", pa.string()),
        ("affidavit_url", pa.string()),
        ("raw_record_json", pa.string()),
    ]
)


@cache
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ward(value):
    value = str(value).strip().upper()
    return {"73": "22A", "74": "22B", "75": "22C"}.get(value, value)


def reservation(value):
    normalized = unicodedata.normalize("NFC", value)
    category = normalized.split("_")[0].split("(")[0].strip()
    if category not in CATEGORY:
        raise ValueError(f"Unknown reservation category: {value}")
    return CATEGORY[category], "महिला" in normalized


def row(year, ward_raw, name, sex, path, number, raw):
    if sex not in SEX:
        raise ValueError(f"Unrecognized recorded sex: {sex!r}")
    return {
        "election_year": year,
        "city": "Patna",
        "office": "municipal_ward_councilor",
        "ward_id": ward(ward_raw),
        "ward_id_source": str(ward_raw),
        "candidate_name": name.strip(),
        "sex_recorded": sex,
        "is_woman": SEX[sex] == "female",
        "source_file": str(path),
        "source_sha256": sha(path),
        "source_row": number,
        "raw_record_json": json.dumps(raw, ensure_ascii=False),
    }


def roster(reference):
    with (reference / "reservations_2017_transcription.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    result = {r["ward_id"]: r for r in rows}
    if len(rows) != 75 or len(result) != 75:
        raise ValueError("Reservation transcription must have 75 unique wards")
    return result


def parse_2017(raw, reference):
    reservations, output, conflicts = roster(reference), [], []
    for page in range(1, 5):
        path = raw / f"winners_2017_page{page}.html"
        soup = BeautifulSoup(path.read_bytes(), "html.parser")
        for tr in soup.select("#gvWard tr"):
            cells = tr.find_all("td", recursive=False)
            if len(cells) != 13:
                continue
            c = [cell.get_text(" ", strip=True) for cell in cells]
            r = row(2017, c[1], c[3], c[5], path, int(c[0]), c)
            notified = reservations[r["ward_id"]]
            category, female = reservation(c[2])
            adopted = (
                notified["reservation_category"],
                notified["is_women_reserved"] == "1",
            )
            if (category, female) != adopted:
                conflicts.append(
                    {
                        "year": 2017,
                        "ward_id": r["ward_id"],
                        "field": "ward_reservation",
                        "winner_grid": c[2],
                        "adopted_category": adopted[0],
                        "adopted_women_reserved": adopted[1],
                        "basis": "signed_reservation_notification",
                        "pdf_page": int(notified["source_pdf_page"]),
                        "pdf_row": int(notified["source_row"]),
                    }
                )
            r.update(
                relative_name=c[4],
                age_reported=int(c[6]),
                age_reference="2017_source_record",
                education_reported=c[8],
                candidate_category=c[7],
                is_winner=True,
                position=1,
                reservation_category=adopted[0],
                is_women_reserved=adopted[1],
                reservation_source_raw=c[2],
                reservation_basis="signed_2017_pdf_transcription",
                source_kind="official_2017_winner_grid",
            )
            output.append(r)
    validate_winners(output, 2017)
    return output, conflicts


def parse_2022(raw):
    path = raw / "winners_2022.json"
    records = json.loads(json.loads(path.read_bytes())["d"])
    output = []
    for number, c in enumerate(records, 1):
        if c["post_id"] != 3 or c["Phase"] != 2 or c["NPNameHn"] != "पटना नगर निगम":
            raise ValueError("Non-Patna ward councilor in 2022 source")
        category, female = reservation(c["ReservedFor"])
        r = row(2022, c["wardno"], c["name_hn"], c["gender"], path, number, c)
        r.update(
            relative_name=c["guardian_name_hn"].strip(),
            age_reported=int(c["age"]),
            age_reference="dynamic_retrieval_year_not_election_age",
            candidate_category=c["cname"],
            is_winner=True,
            position=1,
            reservation_category=category,
            is_women_reserved=female,
            reservation_source_raw=c["ReservedFor"],
            reservation_basis="2022_winner_api",
            source_kind="official_2022_phase2_winner_api",
            affidavit_url=(
                "http://sec2021.bihar.gov.in/ForPublicPdf/SEC_Nomination2/Uploads/"
                f"{c['user_id']}/{c['NomID']}/Documents/aff_prapatra_kh.pdf"
            ),
        )
        output.append(r)
    validate_winners(output, 2022)
    return output


def validate_winners(rows, year):
    expected = {str(n) for n in range(1, 73)} | {"22A", "22B", "22C"}
    if len(rows) != 75 or {r["ward_id"] for r in rows} != expected:
        raise ValueError(f"Incomplete or duplicated {year} winner frame")


def parse_tcpd(path, reference):
    if sha(path) != TCPD_SHA:
        raise ValueError("TCPD source differs from the pinned central receipt")
    reservations, output = roster(reference), []
    with path.open() as stream:
        for number, c in enumerate(csv.DictReader(stream), 2):
            if (c["State_Name"], c["Year"], c["LB_Name"]) != ("Bihar", "2017", "patna"):
                continue
            r = row(
                2017, c["Ward_No"], c["Candidate_Name_O"], c["Gender"], path, number, c
            )
            notified = reservations[r["ward_id"]]
            r.update(
                relative_name=c["Father_Husband_Name_O"],
                age_reported=int(c["Age"]),
                age_reference="2017_source_record",
                education_reported=c["Education"],
                candidate_category=c["Category"],
                votes=int(c["Votes"]),
                position=int(c["Position"]),
                is_winner=c["Position"] == "1",
                reservation_category=notified["reservation_category"],
                is_women_reserved=notified["is_women_reserved"] == "1",
                reservation_source_raw=c["Ward_Reservation"],
                reservation_basis="signed_2017_pdf_transcription",
                source_kind="tcpd_casi_ulb_1.1",
                polling_date_reported=c["Polling_Date"],
            )
            output.append(r)
    if len(output) != 1008:
        raise ValueError("Unexpected TCPD Patna candidate count")
    validate_winners([r for r in output if r["is_winner"]], 2017)
    return output


def build(raw, reference, tcpd, release):
    sha.cache_clear()
    receipts = [
        json.loads(line) for line in (raw / "receipts.jsonl").read_text().splitlines()
    ]
    for r in receipts:
        if r["ok"] and (
            sha(raw / r["file"]) != r["sha256"]
            or (raw / r["file"]).stat().st_size != r["bytes"]
        ):
            raise ValueError(f"Source checksum changed: {r['file']}")
    reference_receipt = json.loads(
        (reference / "transcription_receipt.json").read_text()
    )
    if (
        sha(reference / "reservations_2017_transcription.csv")
        != reference_receipt["sha256"]
    ):
        raise ValueError("Reservation transcription checksum changed")
    if sha(raw / "reservation_2017.pdf") != reference_receipt["source_sha256"]:
        raise ValueError("Reservation transcription source changed")
    first, conflicts = parse_2017(raw, reference)
    second = parse_2022(raw)
    candidates = parse_tcpd(tcpd, reference)
    for r in first + second + candidates:
        r["sex_reservation_conflict"] = r["is_women_reserved"] and not r["is_woman"]
    by_ward = {r["ward_id"]: r for r in first}
    secondary = {r["ward_id"]: r for r in candidates if r["is_winner"]}
    checks = []
    for ward_id, primary in by_ward.items():
        other = secondary[ward_id]
        for field in ["candidate_name", "is_woman", "age_reported"]:
            if primary[field] != other[field]:
                checks.append(
                    {
                        "ward_id": ward_id,
                        "field": field,
                        "official_value": primary[field],
                        "tcpd_value": other[field],
                    }
                )
    release.mkdir(parents=True, exist_ok=True)
    for name, records in [("winners", first + second), ("candidates_2017", candidates)]:
        table = pa.Table.from_pylist(records, schema=SCHEMA)
        pq.write_table(table, release / f"{name}.parquet", compression="zstd")
    transitions = [
        {
            "ward_id": r["ward_id"],
            "year_from": 2017,
            "year_to": 2022,
            "women_reserved_from": by_ward[r["ward_id"]]["is_women_reserved"],
            "women_reserved_to": r["is_women_reserved"],
            "category_from": by_ward[r["ward_id"]]["reservation_category"],
            "category_to": r["reservation_category"],
            "ward_label_link_basis": "2017_22abc_labels_and_2022_ui_aliases_73_74_75",
            "boundary_equivalence_verified": False,
            "post_quota_open_transition": by_ward[r["ward_id"]]["is_women_reserved"]
            and not r["is_women_reserved"],
        }
        for r in second
    ]
    pq.write_table(
        pa.Table.from_pylist(transitions), release / "ward_transitions.parquet"
    )
    (release / "source_conflicts.json").write_text(
        json.dumps(
            {
                "reservation_conflicts": conflicts,
                "tcpd_winner_differences": checks,
                "age_2022": (
                    "API age is retrieval-year dependent; not age at the 2022 election."
                ),
                "tcpd_polling_date": (
                    "21-05-2017 on all rows; not adopted as a verified Patna date."
                ),
                "sex_reservation_conflicts": [
                    {k: r[k] for k in ["election_year", "ward_id", "sex_recorded"]}
                    for r in first + second
                    if r["sex_reservation_conflict"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    profile = {
        str(year): {
            "winners": len(rows),
            "women_winners": sum(r["is_woman"] for r in rows),
            "women_reserved": sum(r["is_women_reserved"] for r in rows),
            "women_in_non_women_reserved": sum(
                r["is_woman"] and not r["is_women_reserved"] for r in rows
            ),
            "education_missing": sum(r.get("education_reported") is None for r in rows),
        }
        for year, rows in [(2017, first), (2022, second)]
    }
    profile.update(
        tcpd_candidates=len(candidates),
        reservation_conflicts=len(conflicts),
        tcpd_winner_differences=len(checks),
        post_quota_open_transitions=sum(
            r["post_quota_open_transition"] for r in transitions
        ),
        reservation_transitions=dict(
            Counter(
                f"{int(r['women_reserved_from'])}->{int(r['women_reserved_to'])}"
                for r in transitions
            )
        ),
    )
    (release / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    schema = {f.name: str(f.type) for f in SCHEMA}
    (release / "schema.json").write_text(json.dumps(schema, indent=2) + "\n")
    files = sorted(
        p for p in release.iterdir() if p.is_file() and p.name != "checksums.sha256"
    )
    (release / "checksums.sha256").write_text(
        "".join(f"{sha(p)}  {p.name}\n" for p in files)
    )
    print(json.dumps(profile, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=RAW)
    parser.add_argument("--reference", type=Path, default=REFERENCE)
    parser.add_argument("--tcpd", type=Path, default=TCPD)
    parser.add_argument("--release", type=Path, default=RELEASE)
    args = parser.parse_args()
    build(args.raw, args.reference, args.tcpd, args.release)


if __name__ == "__main__":
    main()

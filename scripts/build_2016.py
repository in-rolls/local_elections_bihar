"""Build the validated 2016 panchayat release from re-collected results-form pages.

Reads only the frame and result ledgers saved by sec_2016.py (as ledger files or a
tar of them). Every page element that carries data is mapped explicitly; an
unknown label, table header or value outside a declared vocabulary stops the build.
"""

import argparse
import csv
import gzip
import hashlib
import json
import re
import tarfile
from collections import defaultdict
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq
from bs4 import BeautifulSoup
from schemas_2016 import TABLES, dictionary_rows, polars_schema
from sec_2016 import OFFICES, current_page, html_of

HEADER = (
    "Sr No.",
    "Candidate Name",
    "Father/Hubs Name",
    "Gender",
    "Age",
    "Category",
    "Educational Qualification",
    "Mobile No.",
    "Address",
    "Email Id",
    "Obtained Valid Vote",
    "Remarks",
)
COLUMNS = (
    "sr_no",
    "candidate_name",
    "father_husband_name",
    "gender_raw",
    "age",
    "category",
    "education",
    "mobile_number",
    "address",
    "email",
    "votes_raw",
    "remarks",
)
GENDER = {"पुरुष": "male", "महिला": "female", "तृतीय लिंग": "other", "--": None}
MAX_AGE = 120
# A tie broken by drawing lots is shown as the tied count "+1" on the winner's row,
# written three ways: "136+1" (Samastipur ward), "951+1=952" (Supaul sarpanch) and
# "986+1 (BY LAUTARI)=987" (Gopalganj mukhiya). The votes cast are the count before
# the plus; a stated total must be that count plus one.
LOT = re.compile(r"(\d+)\+1(?: \(BY LAUTARI\))?(?:=(\d+))?")
# Blank cells: the form's "--", and a single "-" in a few rows.
BLANK = ("", "-", "--")
# The form's own unset dropdown text, shown where no reservation was recorded.
UNSET_RESERVATION = "--select--"
SPANS = {
    "lblPNKS",
    "lblPradesikForMukhiya",
    "lblReservationStatusForMukhiya",
    "lblResevationShow",
    "lblMsg",
}
NO_RECORD = "Record not Found..!"
KEY = ("office", "district_code", "block_code", "panchayat_code", "unit_code")


def ledgers(source):
    """Yield (name, events) for finished version-2 result ledgers."""

    def events_of(data):
        rows = [json.loads(line) for line in gzip.decompress(data).splitlines()]
        if not rows or not rows[-1].get("done") or rows[-1].get("version") != 2:
            return None
        return rows[:-1]

    paths = [source] if source.is_file() else sorted(source.glob("*"))
    for path in paths:
        if path.suffix == ".tar":
            with tarfile.open(path) as tar:
                for member in tar:
                    name = member.name.rsplit("/", 1)[-1]
                    if name.endswith(".jsonl.gz") and not name.startswith("._"):
                        yield name, events_of(tar.extractfile(member).read())
        elif path.name.endswith(".jsonl.gz"):
            yield path.name, events_of(path.read_bytes())


def parse_page(html, where):
    soup = BeautifulSoup(html, "html.parser")
    spans = {
        s["id"]: " ".join(s.get_text(" ").split())
        for s in soup.select("span[id]")
        if s.get_text(strip=True)
    }
    unknown = set(spans) - SPANS
    if unknown:
        raise ValueError(f"Unmapped page labels {sorted(unknown)} in {where}")
    grid = soup.select_one("#gvVoterListDetails")
    rows = []
    if grid is not None:
        header = tuple(
            c.get_text(" ", strip=True) for c in grid.select("tr")[0].select("th,td")
        )
        if header != HEADER:
            raise ValueError(f"Unexpected results header in {where}: {header}")
        for tr in grid.select("tr")[1:]:
            cells = [
                td.get_text(" ", strip=True)
                for td in tr.find_all("td", recursive=False)
            ]
            if len(cells) == len(HEADER):
                rows.append(dict(zip(COLUMNS, cells, strict=True)))
            elif not tr.select("a[href*='Page$'], span"):
                raise ValueError(f"Unexpected results row in {where}: {cells}")
    if spans.get("lblMsg") not in (None, NO_RECORD):
        raise ValueError(f"Unexpected message in {where}: {spans['lblMsg']}")
    if bool(rows) == (spans.get("lblMsg") == NO_RECORD):
        raise ValueError(f"Page has both or neither results and no-record: {where}")
    reservation = spans.get("lblReservationStatusForMukhiya") or spans.get(
        "lblResevationShow"
    )
    return {
        "seat_label": spans.get("lblPradesikForMukhiya"),
        "seat_reservation": None if reservation == UNSET_RESERVATION else reservation,
        "rows": rows,
    }


def number(value, name, where):
    value = value.strip()
    if value in BLANK:
        return None
    if not value.isdigit():
        raise ValueError(f"Non-numeric {name} {value!r} in {where}")
    return int(value)


def age(value, where):
    """Age as typed, except values no person has: the cell sometimes holds the
    age run into the phone number (229525839157) or a slip such as 4321."""
    years = number(value, "Age", where)
    return None if years is None or years > MAX_AGE else years


def text(value):
    # 13 cells carry a NUL inside a word ("रामच\x00न्द्र"); without it they read as
    # the name (रामचन्द्र), and a NUL breaks most tools that read text.
    value = value.replace("\x00", "").strip()
    return None if value in BLANK else value


def build(frame_path, results, out, partial=False):
    frame = pq.read_table(frame_path).to_pylist()
    pages = defaultdict(dict)
    for name, events in ledgers(results):
        if events is None:
            if partial:
                continue
            raise ValueError(f"Unfinished or page-1-only ledger: {name}")
        for index, event in enumerate(events):
            key = (
                OFFICES[event["office_code"]],
                event["district"],
                event["block"],
                event["panchayat"],
                event["unit"],
            )
            html = html_of(event)
            if current_page(html) != event["page"]:
                raise ValueError(
                    f"Saved page differs from requested page: {name} {index}"
                )
            pages[key][event["page"]] = (name, index, event["fetched_at"], html)
    seats, candidates, winners = [], [], []
    missing, emitted = [], set()
    for unit in frame:
        key = (
            unit["office"],
            unit["district"],
            unit["block"],
            unit["panchayat"],
            unit["unit"],
        )
        seat_pages = pages.get(key)
        if not seat_pages:
            missing.append(key)
            continue
        if sorted(seat_pages) != list(range(1, len(seat_pages) + 1)):
            raise ValueError(f"Non-consecutive pages for {key}")
        parsed, rows = [], []
        for page, (name, index, fetched_at, html) in sorted(seat_pages.items()):
            where = f"{name}#{index}"
            info = parse_page(html, where)
            parsed.append(info)
            sha = hashlib.sha256(html.encode()).hexdigest()
            for row in info["rows"]:
                if row["remarks"] not in ("0", "Uncontested", "Vacant"):
                    raise ValueError(f"Unknown remark {row['remarks']!r} in {where}")
                if row["gender_raw"] not in GENDER:
                    raise ValueError(f"Unknown gender {row['gender_raw']!r} in {where}")
                lot = LOT.fullmatch(row["votes_raw"].strip())
                if lot and lot.group(2) and int(lot.group(2)) != int(lot.group(1)) + 1:
                    raise ValueError(f"Lot total is not count + 1 in {where}")
                votes = lot.group(1) if lot else row["votes_raw"]
                rows.append(
                    {
                        **dict(zip(KEY, key, strict=True)),
                        "row": len(rows) + 1,
                        "sr_no": number(row["sr_no"], "Sr No.", where),
                        "candidate_name": text(row["candidate_name"]),
                        "father_husband_name": text(row["father_husband_name"]),
                        "gender_raw": row["gender_raw"],
                        "gender": GENDER[row["gender_raw"]],
                        "age": age(row["age"], where),
                        "age_raw": text(row["age"]),
                        "category": text(row["category"]),
                        "education": text(row["education"]),
                        "mobile_number": text(row["mobile_number"]),
                        "address": text(row["address"]),
                        "email": text(row["email"]),
                        "votes": number(votes, "votes", where),
                        "votes_raw": row["votes_raw"] or None,
                        "won_by_lot": bool(lot),
                        "remarks": row["remarks"],
                        "page": page,
                        "source_file": name,
                        "source_event": index,
                        "fetched_at": fetched_at,
                        "page_sha256": sha,
                    }
                )
        serials = [r["sr_no"] for r in rows]
        for r in rows:
            r["sr_no_repeated"] = (
                r["sr_no"] is not None and serials.count(r["sr_no"]) > 1
            )
        note = undecidable(rows)
        labels = {(p["seat_label"], p["seat_reservation"]) for p in parsed}
        if len(labels) != 1:
            raise ValueError(f"Seat label changes across pages for {key}")
        seat_label, reservation = labels.pop()
        seats.append(
            {
                **dict(zip(KEY, key, strict=True)),
                "district": unit["district_label"],
                "block": unit["block_label"],
                "panchayat": unit["panchayat_label"],
                "unit": unit["unit_label"],
                "code_repeated": unit["code_repeated"],
                "seat_label": seat_label,
                "seat_reservation": reservation,
                "status": "results" if rows else "no_record",
                "pages": len(seat_pages),
                "candidate_rows": len(rows),
                "winner_note": note,
            }
        )
        # A repeated code is fetched once; its rows are emitted once, not per label.
        if key in emitted:
            continue
        emitted.add(key)
        candidates.extend(rows)
        winner = None if note else decide(rows, key)
        if winner:
            winners.append(winner)
    if missing and not partial:
        raise ValueError(
            f"{len(missing)} frame seats have no saved page, e.g. {missing[:3]}"
        )
    return write(out, {"seats": seats, "candidates": candidates, "winners": winners})


def person(row):
    return (row["sr_no"], row["candidate_name"], row["father_husband_name"])


def undecidable(rows):
    """Why the saved rows cannot name a winner, or None.

    The source repeats some candidates within a seat with different vote counts
    (Sitamarhi mukhiya: each of six candidates twice, 19 and 314, 1147 and 18).
    Whether those are partial counts to add or a superseded entry is not stated,
    so such seats keep every row and get no winner. Nor does a seat whose top
    vote is shared with no lot mark: the form does not say how that tie ended.
    """
    if len({person(r) for r in rows if r["remarks"] == "Uncontested"}) > 1:
        return "several_uncontested"
    votes = {}
    for r in rows:
        if r["sr_no"] is not None:
            votes.setdefault(r["sr_no"], set()).add((person(r), r["votes"]))
    if any(len(v) > 1 for v in votes.values()):
        return "repeated_serial_differs"
    counted = sorted(
        {(person(r), r["votes"]) for r in rows if r["votes"] is not None},
        key=lambda pair: -pair[1],
    )
    drawn = any(r["won_by_lot"] for r in rows)
    if len(counted) > 1 and counted[0][1] == counted[1][1] and not drawn:
        return "tied_top_vote"
    return None


def decide(rows, key):
    """Winner: uncontested, else drawn by lot, else highest vote; none if vacant."""
    # Rows repeated with the same person and votes count once.
    rows = list({(person(r), r["votes"], r["remarks"]): r for r in rows}.values())
    uncontested = [r for r in rows if r["remarks"] == "Uncontested"]
    base = dict(zip(KEY, key, strict=True))
    if uncontested:
        r = uncontested[0]
        return {
            **base,
            **pick(r),
            "winner_basis": "uncontested",
            "tied": False,
            "votes": None,
            "margin": None,
        }
    voted = sorted(
        (r for r in rows if r["votes"] is not None), key=lambda r: -r["votes"]
    )
    if not voted:
        return None
    drawn = [r for r in voted if r["won_by_lot"]]
    if drawn:
        level = [r for r in voted if r["votes"] == voted[0]["votes"]]
        if len(drawn) > 1 or drawn[0] not in level or len(level) < 2:
            raise ValueError(f"Lot mark without a tie for the top vote in {key}")
    top = drawn[0] if drawn else voted[0]
    runner = next((r["votes"] for r in voted if r is not top), None)
    return {
        **base,
        **pick(top),
        "winner_basis": "lot" if drawn else "top_vote",
        "tied": runner == top["votes"],
        "votes": top["votes"],
        "margin": None if runner is None else top["votes"] - runner,
    }


def pick(row):
    columns = ("sr_no", "row", "candidate_name", "gender", "age", "category")
    return {k: row[k] for k in columns}


def write(out, tables):
    out.mkdir(parents=True, exist_ok=True)
    frames = {}
    for name, model in TABLES.items():
        schema = polars_schema(model)
        rows = [{c: r.get(c) for c in schema} for r in tables[name]]
        frames[name] = model.validate(
            pl.DataFrame(rows, schema=schema, orient="row"), lazy=True
        )
    files = []
    for name, df in frames.items():
        path = out / f"{name}.parquet"
        temp = path.with_suffix(".tmp")
        df.write_parquet(temp, compression="zstd", statistics=True)
        temp.replace(path)
        files.append(
            {
                "path": path.name,
                "rows": df.height,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "schema": {c: str(t) for c, t in df.schema.items()},
            }
        )
    with (out / "dictionary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            ["table", "column", "type", "nullable", "checks", "description"],
            lineterminator="\n",
        )
        writer.writeheader()
        for name, model in TABLES.items():
            writer.writerows(dictionary_rows(name, model))
    (out / "SCHEMA.json").write_text(
        json.dumps({f["path"]: f["schema"] for f in files}, indent=2) + "\n"
    )
    (out / "CHECKSUMS").write_text(
        "".join(f"{f['sha256']}  {f['path']}\n" for f in files)
    )
    return files


def verify(out):
    manifest = json.loads((out / "MANIFEST.json").read_text())
    for info in manifest["files"]:
        path = out / info["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError(f"Checksum differs from manifest: {path}")
        df = TABLES[path.stem].validate(pl.read_parquet(path), lazy=True)
        if df.height != info["rows"]:
            raise ValueError(f"Row count differs from manifest: {path}")
    seats = pl.read_parquet(out / "seats.parquet").unique(list(KEY))
    for name in ("candidates", "winners"):
        rows = pl.read_parquet(out / f"{name}.parquet")
        orphans = rows.join(seats, on=list(KEY), how="anti", nulls_equal=True)
        if orphans.height:
            raise ValueError(f"{name} rows without a seat: {orphans.height}")
    print(json.dumps({"verified": True, "files": len(manifest["files"])}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frame", type=Path, default=Path("data/raw/statewide_2016/2016/frame.parquet")
    )
    parser.add_argument(
        "--results", type=Path, default=Path("data/interim/2016/archive")
    )
    parser.add_argument("--out", type=Path, default=Path("data/release/2016_panchayat"))
    parser.add_argument("--check", action="store_true")
    # Development only: build from the pages saved so far, skipping unfetched seats.
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    if args.check:
        verify(args.out)
        return
    files = build(args.frame, args.results, args.out, args.partial)
    manifest = {
        "year": 2016,
        "source": "https://sec.bihar.gov.in/old-sec/ovc.aspx",
        "files": files,
        "frame_sha256": hashlib.sha256(args.frame.read_bytes()).hexdigest(),
        "code_sha256": {
            name: hashlib.sha256(
                (Path(__file__).parent / name).read_bytes()
            ).hexdigest()
            for name in ("build_2016.py", "schemas_2016.py", "sec_2016.py")
        },
    }
    (args.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({f["path"]: f["rows"] for f in files}))
    verify(args.out)


if __name__ == "__main__":
    main()

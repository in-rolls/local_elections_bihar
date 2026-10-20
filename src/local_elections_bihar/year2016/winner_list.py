"""Parse the 2016 Mukhiya winner list (old-sec/wcl.aspx) saved by collect_winner_list.

Writes one row per listed winner, keyed by the seat frame's district, block and
panchayat (unit) codes, and one coverage row per collected block. Each page
element that carries data is mapped explicitly; an unknown header, message or
seat outside the 2016 frame stops the build. `--check` re-verifies the outputs.
"""

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import polars as pl
from bs4 import BeautifulSoup

from local_elections_bihar.shared.schema import dictionary_rows, polars_schema
from local_elections_bihar.year2016.collect import Ledger, html_of
from local_elections_bihar.year2016.collect_winner_list import (
    GRID,
    URL,
    VERSION,
    current_page,
)
from local_elections_bihar.year2016.parse import GENDER, NO_RECORD, age, text
from local_elections_bihar.year2016.schema import WinnerListRecord

HEADER = (
    "SR No.",
    "Panchayat Name",
    "नि० क्षे० सं०",
    "Reservation Status",
    "Candidate Name",
    "Father/Husband Name",
    "Gender",
    "Age",
    "Category",
    "Educational Qualification",
    "Mobile No.",
    "Address",
    "Candidate Photo",
    "Affidavit",
)
KEY = ["district_code", "block_code", "unit_code"]
COVERAGE = (
    "district_code",
    "block_code",
    "block",
    "frame_seats",
    "ovc_no_record_seats",
    "ovc_no_winner_seats",
    "message",
    "pages",
    "listed",
    "listed_no_record_seats",
    "listed_no_winner_seats",
    "source_file",
)


NAMESAKE = re.compile(r"\s*\(\d+\)\s*$")


def fold(value):
    """Case, punctuation and spacing removed; a trailing namesake mark "(1)" too.

    Only punctuation and separators go, by Unicode category: a regex \\W would
    also drop Devanagari vowel signs (रामचन्द्र -> रमचनदर).
    """
    text = NAMESAKE.sub("", unicodedata.normalize("NFC", value or "")).casefold()
    return "".join(c for c in text if unicodedata.category(c)[0] not in "PZ")


def parse_view(html, where):
    soup = BeautifulSoup(html, "html.parser")
    message = soup.select_one("#lblMsg")
    message = message.get_text(" ", strip=True) if message else ""
    if message not in ("", NO_RECORD):
        raise ValueError(f"Unexpected message in {where}: {message!r}")
    grid = soup.select_one(f"#{GRID}")
    rows = []
    if grid is not None:
        trs = grid.select("tr")
        header = tuple(c.get_text(" ", strip=True) for c in trs[0].select("th,td"))
        if header != HEADER:
            raise ValueError(f"Unexpected winner-list header in {where}: {header}")
        for tr in trs[1:]:
            cells = [
                td.get_text(" ", strip=True)
                for td in tr.find_all("td", recursive=False)
            ]
            if len(cells) == len(HEADER):
                rows.append(cells)
            # The pager row, and the rows of the table nested inside it.
            elif not (tr.select("a[href*='Page$']") or tr.find_parent("td")):
                raise ValueError(f"Unexpected winner-list row in {where}: {cells}")
    if bool(rows) == (message == NO_RECORD):
        raise ValueError(f"Page has both or neither rows and no-record: {where}")
    return message, rows


def label_key(label):
    """Seat label compared without case, spacing or zero padding of its number.

    The two forms print the same seat as Shankarpur/MAURAKABIYAHI/01 and /1, or
    Sahebganj/Madhopur  Hajari/5 with one space or two.
    """
    parts = [" ".join(p.split()).casefold() for p in (label or "").split("/")]
    if parts and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]))
    return tuple(parts)


def assign(rows, block_seats, where):
    """Set each winner-list row's frame unit_code, in place, and how it was found.

    The number at the end of the list's seat label is a territorial number, not
    the frame's dropdown code (Bisfi/Bhairva/17 is frame unit 19), so codes are
    never matched. A row is first matched to the seat whose ovc.aspx page printed
    the same label (see label_key); no-record pages print one too, but some
    print none or drop the number (Jhajha/CHAI/). The rest are matched by
    panchayat name to the one unclaimed frame seat of that name in the block.
    Anything else stops the build.
    """
    by_label, by_name = {}, {}
    for unit, label, seat_label in block_seats.select(
        "unit_code", "unit", "seat_label"
    ).iter_rows():
        if seat_label is not None:
            by_label.setdefault(label_key(seat_label), set()).add(unit)
        by_name.setdefault(fold(label.split(" - ", 1)[-1]), set()).add(unit)
    claimed = set()
    for r in rows:
        units = by_label.get(label_key(r["seat_label"]), set())
        if len(units) == 1:
            r["unit_code"], r["match_basis"] = next(iter(units)), "seat_label"
            claimed.add(r["unit_code"])
    for r in rows:
        if "unit_code" in r:
            continue
        units = by_name.get(fold(r["panchayat_name"]), set()) - claimed
        if len(units) != 1:
            raise ValueError(
                f"Winner-list row {r['seat_label']!r} in {where} matches "
                f"{sorted(units) or 'no'} frame seats"
            )
        r["unit_code"], r["match_basis"] = units.pop(), "panchayat_name"
    labels = dict(block_seats.select("unit_code", "unit").iter_rows())
    for r in rows:
        r["label_matches_frame"] = fold(r["panchayat_name"]) == fold(
            labels[r["unit_code"]].split(" - ", 1)[-1]
        )


def build(raw, seats_path, out):
    seats = pl.read_parquet(seats_path).filter(pl.col("office") == "mukhiya")
    records, coverage = [], []
    for path in sorted((raw / "2016/winner_list").glob("*.jsonl.gz")):
        events = Ledger(path).completed(VERSION)
        if events is None:
            raise ValueError(f"Unfinished winner-list ledger: {path}")
        views = [(i, e) for i, e in enumerate(events) if e["step"] == "view"]
        if [e["page"] for _, e in views] != list(range(1, len(views) + 1)):
            raise ValueError(f"Non-consecutive winner-list pages in {path.name}")
        district, block = views[0][1]["district"], views[0][1]["block"]
        messages, block_rows = set(), []
        for index, event in views:
            html = html_of(event)
            if current_page(html) != event["page"]:
                raise ValueError(f"Saved page differs from requested: {path.name}")
            sha = hashlib.sha256(html.encode()).hexdigest()
            message, rows = parse_view(html, f"{path.name}#{index}")
            messages.add(message)
            for number, cells in enumerate(rows, 1):
                (sr, panchayat, seat, reservation, name, father) = cells[:6]
                gender, years, category, education, mobile, address = cells[6:12]
                if gender not in GENDER:
                    raise ValueError(f"Unknown gender {gender!r} in {path.name}")
                block_rows.append(
                    {
                        "district_code": district,
                        "block_code": block,
                        "sr_no": int(sr),
                        "panchayat_name": panchayat,
                        "seat_label": seat,
                        "reserved_raw": text(reservation),
                        "winner_name": text(name),
                        "father_husband_name": text(father),
                        "candidate_woman_raw": gender,
                        "candidate_woman": GENDER[gender],
                        "age": age(years, path.name),
                        "age_raw": text(years),
                        "candidate_caste_raw": text(category),
                        "education": text(education),
                        "mobile_number": text(mobile),
                        "address": text(address),
                        "source_file": path.name,
                        "source_event": index,
                        "page": event["page"],
                        "source_row": number,
                        "fetched_at": event["fetched_at"],
                        "page_sha256": sha,
                    }
                )
        if len(messages) != 1:
            raise ValueError(f"Pages disagree on no-record in {path.name}")
        message = messages.pop()
        block_seats = seats.filter(
            pl.col("district_code") == district, pl.col("block_code") == block
        )
        assign(block_rows, block_seats, path.name)
        listed = {(district, block, r["unit_code"]) for r in block_rows}
        units = [r["unit_code"] for r in block_rows]
        for r in block_rows:
            r["unit_repeated"] = units.count(r["unit_code"]) > 1
        records.extend(block_rows)
        no_record = {
            k
            for k, s in zip(
                block_seats.select(KEY).iter_rows(),
                block_seats["status"],
                strict=True,
            )
            if s == "no_record"
        }
        no_winner = set(
            block_seats.filter(pl.col("winner_note").is_not_null())
            .select(KEY)
            .iter_rows()
        )
        coverage.append(
            {
                "district_code": district,
                "block_code": block,
                "block": block_seats["block"][0],
                "frame_seats": block_seats.height,
                "ovc_no_record_seats": len(no_record),
                "ovc_no_winner_seats": len(no_winner),
                "message": message or None,
                "pages": len(views),
                "listed": len(block_rows),
                "listed_no_record_seats": len(listed & no_record),
                "listed_no_winner_seats": len(listed & no_winner),
                "source_file": path.name,
            }
        )
    if not coverage:
        raise ValueError("No winner-list ledgers found")
    schema = polars_schema(WinnerListRecord)
    df = pl.DataFrame(
        [{c: r[c] for c in schema} for r in records], schema=schema, orient="row"
    )
    df = WinnerListRecord.validate(df, lazy=True)
    out.mkdir(parents=True, exist_ok=True)
    table = out / "winner_list_records.parquet"
    df.write_parquet(table, compression="zstd", statistics=True)
    published = seats_path.parent
    candidates = pl.read_parquet(published / "candidates.parquet").filter(
        pl.col("office") == "mukhiya"
    )
    winners = pl.read_parquet(published / "winners.parquet").filter(
        pl.col("office") == "mukhiya"
    )
    tables = {
        "coverage.csv": (COVERAGE, coverage),
        "comparison.csv": (COMPARISON, compare(df, winners)),
        "no_winner_review.csv": (REVIEW, review(df, seats, candidates)),
    }
    for name, (columns, rows) in tables.items():
        with (out / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    ledgers = sorted((raw / "2016/winner_list").glob("*.jsonl.gz"))
    manifest = {
        "year": 2016,
        "source": URL,
        "files": [
            {
                "path": table.name,
                "rows": df.height,
                "sha256": digest(table),
                "columns": {
                    r["column"]: {
                        k: v for k, v in r.items() if k not in {"table", "column"}
                    }
                    for r in dictionary_rows(table.name, WinnerListRecord)
                },
            },
            *(
                {"path": name, "rows": len(rows), "sha256": digest(out / name)}
                for name, (_, rows) in tables.items()
            ),
        ],
        "inputs_sha256": {
            name: digest(published / name)
            for name in ("seats.parquet", "candidates.parquet", "winners.parquet")
        },
        "source_ledgers": {p.name: digest(p) for p in ledgers},
        "code_sha256": {
            name: digest(Path(__file__).resolve().parents[1] / name)
            for name in (
                "year2016/winner_list.py",
                "year2016/collect_winner_list.py",
                "year2016/collect.py",
                "year2016/schema.py",
            )
        },
    }
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps({"records": df.height, "blocks": len(coverage)}))


COMPARISON = (
    "district_code",
    "block_code",
    "unit_code",
    "ovc_sr_no",
    "ovc_winner",
    "wcl_sr_no",
    "wcl_winner",
    "agree_verbatim",
    "agree_folded",
)


def compare(records, winners):
    """Winner-list name against the ovc.aspx-derived winner, seat by seat.

    Covers every listed seat that also has a winner in winners.parquet; a seat
    listed twice gives two rows.
    """
    joined = records.join(winners, on=KEY, how="inner").sort([*KEY, "sr_no"])
    return [
        {
            "district_code": r["district_code"],
            "block_code": r["block_code"],
            "unit_code": r["unit_code"],
            "ovc_sr_no": r["sr_no_right"],
            "ovc_winner": r["candidate_name"],
            "wcl_sr_no": r["sr_no"],
            "wcl_winner": r["winner_name"],
            "agree_verbatim": r["winner_name"] == r["candidate_name"],
            "agree_folded": fold(r["winner_name"]) == fold(r["candidate_name"]),
        }
        for r in joined.iter_rows(named=True)
    ]


REVIEW = (
    "district_code",
    "block_code",
    "unit_code",
    "block",
    "unit",
    "winner_note",
    "candidate_rows",
    "leader_sr_no",
    "leader_name",
    "leader_floor",
    "rival_sr_no",
    "rival_ceiling",
    "leader_variants",
    "wcl_rows",
    "wcl_names",
    "decision",
    "proposed_sr_no",
    "proposed_winner",
    "reason",
    "review_status",
)


def review(records, seats, candidates):
    """Evidence and a rule-based decision for each seat whose rows name no winner.

    Rows are grouped into candidates by serial. A candidate's floor is the lowest
    count among its rows and its ceiling the sum of them, the reading in which
    repeated rows are partial counts. The leader has the highest floor; it wins
    under any reading if that floor exceeds every rival's ceiling. The winner list
    (wcl.aspx) is reported beside this but is not independent: it reads the same
    records and repeats their duplicates. Decisions are proposals for review.
    """
    out = []
    for seat in seats.filter(pl.col("winner_note").is_not_null()).sort(KEY).to_dicts():
        where = [pl.col(k) == seat[k] for k in KEY]
        rows = candidates.filter(*where).to_dicts()
        groups = {}
        for r in rows:
            ident = r["sr_no"] if r["sr_no"] is not None else r["candidate_name"]
            groups.setdefault(ident, []).append(r)
        bounds = []
        for ident, members in groups.items():
            votes = [m["votes"] for m in members if m["votes"] is not None]
            if votes:
                bounds.append((min(votes), sum(votes), ident, members))
        bounds.sort(key=lambda b: (-b[0], str(b[2])))
        floor, _, leader, members = bounds[0]
        rival = max(bounds[1:], key=lambda b: b[1], default=None)
        robust = rival is None or floor > rival[1]
        variants = sorted(
            {(m["candidate_name"], m["father_husband_name"]) for m in members}
        )
        names = records.filter(*where)["winner_name"].to_list()
        leader_names = {fold(m["candidate_name"]) for m in members}
        if not robust:
            decision = "undecided"
            reason = (
                f"leader floor {floor} does not exceed rival ceiling {rival[1]}; "
                "the result depends on how the repeated rows are read"
            )
        elif not names:
            decision = "votes_only"
            reason = f"floor {floor} exceeds every rival ceiling; no winner-list row"
        elif any(fold(n) not in leader_names for n in names):
            decision = "conflict"
            reason = "the winner list names someone other than the vote leader"
        elif len(variants) > 1:
            decision = "supported_if_same_person"
            reason = (
                f"floor {floor} exceeds every rival ceiling and the winner list "
                "agrees, provided the leader's rows, which share a serial but "
                "differ in name or father/husband name, are one person"
            )
        else:
            decision = "supported"
            reason = (
                f"floor {floor} exceeds every rival ceiling "
                f"({'none' if rival is None else rival[1]}); winner list agrees"
            )
        proposed = decision in ("supported", "supported_if_same_person")
        out.append(
            {
                **{k: seat[k] for k in KEY},
                "block": seat["block"],
                "unit": seat["unit"],
                "winner_note": seat["winner_note"],
                "candidate_rows": len(rows),
                "leader_sr_no": leader,
                "leader_name": members[0]["candidate_name"],
                "leader_floor": floor,
                "rival_sr_no": None if rival is None else rival[2],
                "rival_ceiling": None if rival is None else rival[1],
                "leader_variants": " | ".join(f"{n} / {f}" for n, f in variants),
                "wcl_rows": len(names),
                "wcl_names": " | ".join(names),
                "decision": decision,
                "proposed_sr_no": leader if proposed else None,
                "proposed_winner": members[0]["candidate_name"] if proposed else None,
                "reason": reason,
                "review_status": "unreviewed",
            }
        )
    return out


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(out, seats_path):
    manifest = json.loads((out / "MANIFEST.json").read_text())
    for info in manifest["files"]:
        if digest(out / info["path"]) != info["sha256"]:
            raise ValueError(f"Checksum differs from manifest: {out / info['path']}")
    df = pl.read_parquet(out / "winner_list_records.parquet")
    if df.schema != pl.Schema(polars_schema(WinnerListRecord)):
        raise ValueError(f"Winner-list dtypes differ from the schema: {df.schema}")
    df = WinnerListRecord.validate(df, lazy=True)
    repeated = df.select(KEY).is_duplicated()
    if not repeated.equals(df["unit_repeated"], check_names=False):
        raise ValueError("Repeated seats differ from unit_repeated")
    seats = pl.read_parquet(seats_path).filter(pl.col("office") == "mukhiya")
    orphans = df.join(seats.select(KEY).unique(), on=KEY, how="anti")
    if orphans.height:
        raise ValueError(f"Winner-list rows outside the 2016 frame: {orphans.height}")
    print(json.dumps({"verified": True, "records": df.height}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/2016/raw/statewide"))
    parser.add_argument("--seats", type=Path, default=Path("data/2016/seats.parquet"))
    parser.add_argument("--out", type=Path, default=Path("data/2016/winner_list"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        build(args.raw, args.seats, args.out)
    verify(args.out, args.seats)


if __name__ == "__main__":
    main()

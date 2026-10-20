"""Synthetic 2016 winner-list (wcl.aspx) pages and no-winner review; no requests."""

from pathlib import Path

import polars as pl
import pytest

from local_elections_bihar.year2016 import winner_list as w
from local_elections_bihar.year2016.collect import Ledger, record
from local_elections_bihar.year2016.schema import Candidate, Seat

HEADER = "".join(f"<th>{h}</th>" for h in w.HEADER)
PAGER = "javascript:__doPostBack('gvMukhiyaSarpanch','"


def row(sr, panchayat, code, name):
    seat = f"Arwal/{panchayat}/{code}"
    person = [name, "F", "महिला", "40", "अन्य", "Literate", "0990", "A"]
    return [sr, panchayat, seat, "अनारक्षित", *person, "", "Affidavit"]


def page(rows=(), number=1, pages=1, message=""):
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    if pages > 1:
        links = "".join(
            f"<td><span>{n}</span></td>"
            if n == number
            else f'<td><a href="{PAGER}Page${n}\')">{n}</a></td>'
            for n in range(1, pages + 1)
        )
        body += f'<tr><td colspan="14"><table><tr>{links}</tr></table></td></tr>'
    grid = f'<table id="gvMukhiyaSarpanch"><tr>{HEADER}</tr>{body}</table>'
    return (
        '<input type="hidden" name="__VIEWSTATE" value="x">'
        f'<span id="lblMsg">{message}</span>{grid if rows else ""}'
    )


def test_fold_keeps_devanagari_vowel_signs_and_drops_namesake_mark():
    assert w.fold("रामचन्द्र  देवी") == "रामचन्द्रदेवी"
    assert w.fold("Anita Devi (1)") == w.fold("ANITA DEVI")
    assert w.fold("रामचन्द्र") != w.fold("रमचनदर")


def test_parse_view_reads_rows_skips_pager_and_rejects_unknown_message():
    message, rows = w.parse_view(page([row(1, "P", "01", "A")], 1, 2), "t")
    assert message == "" and len(rows) == 1 and rows[0][4] == "A"
    message, rows = w.parse_view(page(message=w.NO_RECORD), "t")
    assert message == w.NO_RECORD and rows == []
    with pytest.raises(ValueError, match="Unexpected message"):
        w.parse_view(page(message="Server busy"), "t")
    with pytest.raises(ValueError, match="both or neither"):
        w.parse_view(page(), "t")


def test_label_key_ignores_padding_case_and_spacing_only():
    assert w.label_key("Shankarpur/MAURAKABIYAHI/01") == w.label_key(
        "shankarpur/MAURAKABIYAHI/1"
    )
    assert w.label_key("Sahebganj/Madhopur  Hajari/5") == w.label_key(
        "Sahebganj/Madhopur Hajari/5"
    )
    assert w.label_key("Bisfi/Bhairva/17") != w.label_key("Bisfi/Bhairva/19")


def seats_frame(units, notes=None, labels=None):
    notes = notes or {}
    rows = [
        {
            "office": "mukhiya",
            "district_code": "33",
            "block_code": "001",
            "panchayat_code": None,
            "unit_code": u,
            "district": "33 - ARWAL",
            "block": "001 - Arwal",
            "panchayat": None,
            "unit": f"{u} - {label}",
            "code_repeated": False,
            "seat_label": (labels or {}).get(u),
            "seat_reservation": None,
            "status": "results",
            "pages": 1,
            "candidate_rows": 1,
            "winner_note": notes.get(u),
        }
        for u, label in units
    ]
    schema = {k: v.dtype.type for k, v in Seat.to_schema().columns.items()}
    return pl.DataFrame(rows, schema=schema, orient="row")


def candidates_frame(unit, rows):
    schema = {k: v.dtype.type for k, v in Candidate.to_schema().columns.items()}
    out = []
    for i, (sr, name, father, votes) in enumerate(rows, 1):
        base = dict.fromkeys(schema)
        base.update(
            office="mukhiya",
            district_code="33",
            block_code="001",
            unit_code=unit,
            row=i,
            sr_no=sr,
            candidate_name=name,
            father_husband_name=father,
            votes=votes,
        )
        out.append(base)
    return pl.DataFrame(out, schema=schema, orient="row")


def write_ledger(raw, pages):
    events = [record("block", {"district": "33", "block": "001"}, "x")]
    for number, html in enumerate(pages, 1):
        values = {"district": "33", "block": "001", "page": number}
        events.append(record("view", values, html))
    path = raw / "2016/winner_list/mukhiya_d33_b001.jsonl.gz"
    Ledger(path).write(events, w.VERSION)


def published(tmp_path, seats, candidates):
    out = tmp_path / "2016"
    out.mkdir()
    seats.write_parquet(out / "seats.parquet")
    candidates.write_parquet(out / "candidates.parquet")
    winners = candidates.head(0).select(
        "office", *w.KEY[:2], "panchayat_code", "unit_code", "sr_no", "candidate_name"
    )
    winners.write_parquet(out / "winners.parquet")
    return out / "seats.parquet"


def test_build_matches_by_label_then_name_flags_repeats_and_checks(tmp_path):
    # Unit 01's territorial number is 7, not its code: only the label ties it.
    # Unit 02 carries no ovc label (no-record page), so its name does.
    seats = seats_frame(
        [("01", "ONE"), ("02", "TWO"), ("03", "THREE")],
        {"02": "repeated_serial_differs"},
        {"01": "Arwal/ONE/7", "03": "Arwal/THREE/1"},
    )
    candidates = candidates_frame(
        "02",
        [
            (1, "RAMITA DEVI", "VIJAY", 693),
            (1, "RAMITA DEVI", "VINAY", 693),
            (2, "GITA DEVI", "S", 680),
        ],
    )
    seats_path = published(tmp_path, seats, candidates)
    raw, out = tmp_path / "raw", tmp_path / "out"
    first = [row(1, "ONE", "07", "A")]
    second = [row(2, "TWO", "02", "RAMITA DEVI"), row(3, "TWO", "02", "RAMITA DEVI")]
    write_ledger(raw, [page(first, 1, 2), page(second, 2, 2)])
    w.build(raw, seats_path, out)
    w.verify(out, seats_path)
    df = pl.read_parquet(out / "winner_list_records.parquet")
    assert df["unit_code"].to_list() == ["01", "02", "02"]
    assert df["match_basis"].to_list() == ["seat_label", *["panchayat_name"] * 2]
    assert df["seat_label"][0] == "Arwal/ONE/07"
    assert df["unit_repeated"].to_list() == [False, True, True]
    assert df["label_matches_frame"].all()
    assert df["page"].to_list() == [1, 2, 2]
    review = pl.read_csv(out / "no_winner_review.csv")
    assert review["decision"].to_list() == ["supported_if_same_person"]
    assert review["proposed_winner"].to_list() == ["RAMITA DEVI"]


def test_build_rejects_a_seat_outside_the_frame(tmp_path):
    seats = seats_frame([("01", "ONE")])
    seats_path = published(tmp_path, seats, candidates_frame("01", []))
    raw = tmp_path / "raw"
    write_ledger(raw, [page([row(1, "NINE", "09", "A")])])
    with pytest.raises(ValueError, match="matches no frame seats"):
        w.build(raw, seats_path, tmp_path / "out")


@pytest.mark.parametrize(
    ("rows", "listed", "decision"),
    [
        # Repeated rival far behind: leader wins under any reading.
        (
            [(1, "A", "F", 2414), (2, "B", "G", 1048), (2, "B", "G", 1078)],
            ["A"],
            "supported",
        ),
        # Every candidate twice; summing could reverse the order.
        (
            [
                (1, "A", "F", 500),
                (1, "A", "F", 20),
                (2, "B", "G", 400),
                (2, "B", "G", 300),
            ],
            ["A"],
            "undecided",
        ),
        ([(1, "A", "F", 900), (2, "B", "G", 10), (2, "B", "G", 12)], ["B"], "conflict"),
        ([(1, "A", "F", 900), (2, "B", "G", 10), (2, "B", "G", 12)], [], "votes_only"),
    ],
)
def test_review_decisions(rows, listed, decision):
    seats = seats_frame([("02", "TWO")], {"02": "repeated_serial_differs"})
    records = pl.DataFrame(
        {
            "district_code": ["33"] * len(listed),
            "block_code": ["001"] * len(listed),
            "unit_code": ["02"] * len(listed),
            "winner_name": listed,
        },
        schema={
            "district_code": pl.Utf8,
            "block_code": pl.Utf8,
            "unit_code": pl.Utf8,
            "winner_name": pl.Utf8,
        },
    )
    result = w.review(records, seats, candidates_frame("02", rows))
    assert [r["decision"] for r in result] == [decision]


def test_reviewed_rulings_accept_only_robust_leaders():
    """Every accepted ruling names the leader the vote rule makes robust."""
    base = Path(__file__).resolve().parents[1] / "data/2016/winner_list"
    review = pl.read_csv(base / "no_winner_review.csv", infer_schema_length=0)
    ruled = pl.read_csv(base / "no_winner_reviewed.csv", infer_schema_length=0)
    key = ["district_code", "block_code", "unit_code"]
    assert ruled.select(key).is_unique().all()
    assert ruled.height == review.height
    joined = ruled.join(review, on=key, how="inner")
    accepted = joined.filter(pl.col("decision") == "accept")
    assert (
        accepted["decision_right"]
        .is_in(["supported", "supported_if_same_person"])
        .all()
    )
    assert (accepted["winner_sr_no"] == accepted["leader_sr_no"]).all()
    undecided = joined.filter(pl.col("decision") == "undecided")
    assert (undecided["decision_right"] == "undecided").all()

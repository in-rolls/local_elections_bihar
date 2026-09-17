"""Synthetic 2016 results-form pages; no live requests."""

import base64
import gzip
import json

import build_2016 as b
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

HEADER = "".join(f"<th>{h}</th>" for h in b.HEADER)
PAGER = "javascript:__doPostBack('gvVoterListDetails','"


def page(rows=(), number=1, pages=1, message=None, seat="Arwal/sonbarsa/1"):
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    if pages > 1:
        links = "".join(
            f"<td><span>{n}</span></td>"
            if n == number
            else f'<td><a href="{PAGER}Page${n}\')">{n}</a></td>'
            for n in range(1, pages + 1)
        )
        body += f'<tr><td colspan="12"><table><tr>{links}</tr></table></td></tr>'
    grid = (
        f'<table id="gvVoterListDetails"><tr>{HEADER}</tr>{body}</table>'
        if rows
        else ""
    )
    msg = f'<span id="lblMsg">{message}</span>' if message else ""
    return (
        '<input type="hidden" name="__VIEWSTATE" value="x">'
        f'<span id="lblPradesikForMukhiya">{seat}</span>'
        '<span id="lblReservationStatusForMukhiya">अनारक्षित</span>'
        f"{msg}{grid}"
    )


def candidate(sr, name, votes, remark="0", gender="महिला", age="40"):
    return [
        sr,
        name,
        "G",
        gender,
        age,
        "पिछड़ा वर्ग",
        "Inter",
        "0990",
        "A",
        "",
        votes,
        remark,
    ]


def write_inputs(tmp_path, views):
    frame = [
        {
            "office": "mukhiya",
            "office_code": "0107",
            "district": "33",
            "district_label": "33 - ARWAL",
            "block": "001",
            "block_label": "001 - Arwal",
            "panchayat": None,
            "panchayat_label": None,
            "unit": unit,
            "unit_label": f"{unit} - P",
            "code_repeated": False,
        }
        for unit in sorted({v[0] for v in views})
    ]
    frame_path = tmp_path / "frame.parquet"
    pq.write_table(pa.Table.from_pylist(frame), frame_path)
    events = [
        {
            "step": "view",
            "office_code": "0107",
            "district": "33",
            "block": "001",
            "panchayat": None,
            "unit": unit,
            "page": number,
            "fetched_at": "2026-09-15T00:00:00+00:00",
            "html_gzip_base64": base64.b64encode(gzip.compress(html.encode())).decode(),
        }
        for unit, number, html in views
    ]
    results = tmp_path / "results"
    results.mkdir()
    lines = [json.dumps(e) for e in events] + [json.dumps({"done": True, "version": 2})]
    (results / "mukhiya_d33_b001.jsonl.gz").write_bytes(
        gzip.compress(("\n".join(lines) + "\n").encode())
    )
    return frame_path, results


def test_pages_no_record_uncontested_and_vacant(tmp_path):
    first = [candidate(str(n), f"C{n}", str(100 - n)) for n in range(1, 21)]
    views = [
        ("01", 1, page(first, number=1, pages=2)),
        ("01", 2, page([candidate("21", "C21", "500")], number=2, pages=2)),
        ("02", 1, page(message=b.NO_RECORD)),
        ("03", 1, page([candidate("1", "U", "--", "Uncontested")])),
        ("04", 1, page([candidate("1", "", "--", "Vacant", gender="--", age="--")])),
    ]
    frame, results = write_inputs(tmp_path, views)
    b.build(frame, results, tmp_path / "out")
    seats = pl.read_parquet(tmp_path / "out/seats.parquet").sort("unit_code")
    assert seats["status"].to_list() == ["results", "no_record", "results", "results"]
    assert seats["candidate_rows"].to_list() == [21, 0, 1, 1]
    winners = pl.read_parquet(tmp_path / "out/winners.parquet").sort("unit_code")
    assert winners["unit_code"].to_list() == ["01", "03"]
    assert winners.row(0, named=True)["sr_no"] == 21
    assert winners.row(0, named=True)["margin"] == 500 - 99
    assert winners.row(1, named=True)["winner_basis"] == "uncontested"
    vacant = pl.read_parquet(tmp_path / "out/candidates.parquet").filter(
        pl.col("remarks") == "Vacant"
    )
    assert vacant.row(0, named=True)["gender"] is None
    assert vacant.row(0, named=True)["mobile_number"] == "0990"


def test_unknown_label_header_and_remark_stop_the_build(tmp_path):
    extra = page([candidate("1", "C", "5")]) + '<span id="lblNew">x</span>'
    with pytest.raises(ValueError, match="Unmapped page labels"):
        b.parse_page(extra, "t")
    with pytest.raises(ValueError, match="Unexpected results header"):
        b.parse_page(page([candidate("1", "C", "5")]).replace("Remarks", "Note"), "t")
    frame, results = write_inputs(
        tmp_path, [("01", 1, page([candidate("1", "C", "5", "Won")]))]
    )
    with pytest.raises(ValueError, match="Unknown remark"):
        b.build(frame, results, tmp_path / "out")


def test_seat_without_saved_page_fails(tmp_path):
    frame, results = write_inputs(
        tmp_path, [("01", 1, page([candidate("1", "C", "5")]))]
    )
    rows = pq.read_table(frame).to_pylist()
    rows.append(rows[0] | {"unit": "02", "unit_label": "02 - Q"})
    pq.write_table(pa.Table.from_pylist(rows), frame)
    with pytest.raises(ValueError, match="no saved page"):
        b.build(frame, results, tmp_path / "out")


def test_lot_mark_third_gender_and_unset_reservation(tmp_path):
    tie = [
        candidate("1", "A", "136"),
        candidate("2", "B", "136+1", gender="तृतीय लिंग"),
        candidate("3", "C", "90"),
    ]
    unset = page([candidate("1", "D", "7", age="229525839157")]).replace(
        ">अनारक्षित<", ">--select--<"
    )
    frame, results = write_inputs(tmp_path, [("01", 1, page(tie)), ("02", 1, unset)])
    b.build(frame, results, tmp_path / "out")
    winner = pl.read_parquet(tmp_path / "out/winners.parquet").sort("unit_code")
    first = winner.row(0, named=True)
    assert (first["sr_no"], first["winner_basis"], first["votes"]) == (2, "lot", 136)
    assert first["tied"] and first["margin"] == 0 and first["gender"] == "other"
    rows = pl.read_parquet(tmp_path / "out/candidates.parquet").sort(
        "unit_code", "sr_no"
    )
    assert rows["won_by_lot"].to_list() == [False, True, False, False]
    assert rows["votes_raw"][1] == "136+1"
    assert rows["age"].to_list() == [40, 40, 40, None]
    assert rows["age_raw"][3] == "229525839157"
    seats = pl.read_parquet(tmp_path / "out/seats.parquet").sort("unit_code")
    assert seats["seat_reservation"].to_list() == ["अनारक्षित", None]


def test_lot_mark_below_the_top_vote_stops_the_build(tmp_path):
    rows = [candidate("1", "A", "200"), candidate("2", "B", "136+1")]
    frame, results = write_inputs(tmp_path, [("01", 1, page(rows))])
    with pytest.raises(ValueError, match="Lot mark without a tie"):
        b.build(frame, results, tmp_path / "out")


def test_repeated_serials_keep_rows_and_name_no_winner_when_votes_differ(tmp_path):
    differs = [candidate("1", "A", "19"), candidate("1", "A", "314")]
    same = [
        candidate("1", "A", "07"),
        candidate("1", "A", "7"),
        candidate("2", "B", "3"),
    ]
    two = [
        candidate("1", "A", "--", "Uncontested"),
        candidate("2", "B", "--", "Uncontested"),
    ]
    views = [("01", 1, page(differs)), ("02", 1, page(same)), ("03", 1, page(two))]
    frame, results = write_inputs(tmp_path, views)
    b.build(frame, results, tmp_path / "out")
    seats = pl.read_parquet(tmp_path / "out/seats.parquet").sort("unit_code")
    assert seats["winner_note"].to_list() == [
        "repeated_serial_differs",
        None,
        "several_uncontested",
    ]
    assert seats["candidate_rows"].to_list() == [2, 3, 2]
    winners = pl.read_parquet(tmp_path / "out/winners.parquet")
    assert winners["unit_code"].to_list() == ["02"]
    assert not winners["tied"][0] and winners["margin"][0] == 4
    rows = pl.read_parquet(tmp_path / "out/candidates.parquet").sort("unit_code", "row")
    assert rows["sr_no_repeated"].to_list() == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
    ]

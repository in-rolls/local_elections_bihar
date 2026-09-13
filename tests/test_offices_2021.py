"""Synthetic source contracts for the non-mukhiya 2021 offices; no live requests."""

import json

import offices_2021
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from test_sec_portal import archive


def seat(post, seat_no, panchayat_id=None, block_id=1):
    u = {
        "post_id": post,
        "district_id": 33,
        "block_id": block_id,
        "panchayat_id": panchayat_id,
        "seat_no": seat_no,
        "district": "D",
        "block": "B",
        "panchayat": None,
    }
    return {**u, "unit_id": offices_2021.unit_id(u)}


def write_frame(raw, units):
    path = raw / offices_2021.ROOT / "frame.parquet"
    path.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(units), path)


def result(panchayat, serial, votes, won, ward=1, block=1):
    return {
        "Dist": 33,
        "BlockID": block,
        "PanchayatNo": panchayat,
        "PanchayatName": "P",
        "WardNo": ward,
        "OrderBy": serial,
        "CandidateName": " Synthetic (विजेता)" if won else " Synthetic",
        "TotalVote": votes,
        "IsWin": won,
    }


def candidate(post, serial):
    return {
        "PostId": post,
        "OrderBy": serial,
        "CandidateName": "Synthetic",
        "Age": 40,
        "Gender": "महिला",
        "MobileNo": "9999999999",
    }


def test_request_parameters_follow_portal_form():
    assert offices_2021.request_params(seat(1, 7, 12)) == {
        "postId": 1,
        "districtId": 33,
        "blockId": 1,
        "panchayatId": 12,
        "ward": 7,
        "psn": -1,
        "jpn": -1,
    }
    zila = seat(6, 3, block_id=None)
    assert offices_2021.request_params(zila)["blockId"] == ""
    assert offices_2021.request_params(zila)["jpn"] == 3
    assert zila["unit_id"] == "d33_z3"


def test_zila_results_split_by_panchayat_and_phone_removed(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    u = seat(6, 1, block_id=None)
    write_frame(raw, [u])
    base = raw / offices_2021.ROOT / "p6"
    archive(base / "phases" / "d33_z1.jsonl.gz", [{"i": "2021_1", "n": "2021"}])
    archive(
        base / "candidates" / "d33_z1.jsonl.gz",
        [candidate(6, 1), candidate(6, 2)],
        phase="2021_1",
    )
    rows = [
        result(11, 1, 100, True),
        result(11, 2, 150, False),
        result(12, 1, 200, True, block=2),
        result(12, 2, 10, False, block=2),
    ]
    archive(base / "results" / "d33_z1.jsonl.gz", rows, phase="2021_1")
    offices_2021.parse(raw, out)
    parsed = pq.read_table(out / "result_rows.parquet").to_pylist()
    assert [r["result_panchayat_id"] for r in parsed] == [11, 11, 12, 12]
    listed = pq.read_table(out / "candidates.parquet").to_pylist()
    assert all("MobileNo" not in json.loads(c["raw_cell"]) for c in listed)
    coverage = pq.read_table(out / "coverage.parquet").to_pylist()[0]
    assert coverage["phase_2021_listed"] is True
    assert coverage["result_records"] == 4

    rows[0]["WardNo"] = 2
    archive(base / "results" / "d33_z1.jsonl.gz", rows, phase="2021_1")
    with pytest.raises(ValueError, match="outside requested seat"):
        offices_2021.parse(raw, out)


def test_ward_result_must_match_ward_and_phase(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    u = seat(1, 4, 12)
    write_frame(raw, [u])
    path = raw / offices_2021.ROOT / "p1" / "results" / f"{u['unit_id']}.jsonl.gz"
    archive(path, [result(12, 1, 5, True, ward=4)], phase="2021_1")
    offices_2021.parse(raw, out)
    archive(path, [result(12, 1, 5, True, ward=5)], phase="2021_1")
    with pytest.raises(ValueError, match="outside requested seat"):
        offices_2021.parse(raw, out)
    archive(path, [result(12, 1, 5, True, ward=4)], phase="2026_1")
    with pytest.raises(ValueError, match="phase"):
        offices_2021.parse(raw, out)


def test_current_feed_must_match_requested_panchayat(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    write_frame(raw, [])
    winner = {
        "Dist": 33,
        "BlockID": 1,
        "PanchayatNo": 12,
        "WardNo": 3,
        "Post": "Ward member",
        "CandidateName": "Synthetic",
        "MobileNo": "9999999999",
        "Age": 30,
    }
    path = raw / "current/winners/p1/d33_b1_p12.jsonl.gz"
    archive(path, [winner])
    offices_2021.parse(raw, out)
    row = pq.read_table(out / "current_winners.parquet").to_pylist()[0]
    assert row["seat_no"] == 3 and "MobileNo" not in json.loads(row["raw_cell"])
    winner["PanchayatNo"] = 13
    archive(path, [winner])
    with pytest.raises(ValueError, match="outside panchayat"):
        offices_2021.parse(raw, out)

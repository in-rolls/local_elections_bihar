"""Synthetic source contracts; no requests to the live SEC service."""

import base64
import gzip
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import sec_2021
from sec_portal import attributes, completed, decode_records, parse, retry_after


def archive(path, data, phase=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "ok": True,
        "url": "https://example.test",
        "fetched_at": "2026-09-10T00:00:00+00:00",
        "params": {"phase": phase},
        "body_base64": base64.b64encode(json.dumps(data).encode()).decode(),
    }
    with gzip.open(path, "wt") as stream:
        stream.write(json.dumps(event) + "\n" + json.dumps({"done": True}) + "\n")


def test_double_encoded_json_and_error_pages():
    rows = [{"Dist": 1}]
    assert decode_records(json.dumps(json.dumps(rows))) == rows
    assert decode_records('"[]"') == []
    for bad in ["<html>error</html>", "{}", "[1]"]:
        with pytest.raises(ValueError):
            decode_records(bad)


def test_truncated_checkpoint_never_counts_as_completed(tmp_path):
    path = tmp_path / "record.gz"
    archive(path, [{"Dist": 1}])
    assert completed(path)
    path.write_bytes(path.read_bytes()[:-5])
    assert completed(path) is None
    assert completed(tmp_path / "missing.gz") is None


def test_source_categories_and_unknown_year_remain_separate(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    frame = [
        {
            "district_id": 33,
            "district": "D",
            "block_id": 1,
            "block": "B",
            "post_id": 3,
            "post": "Mukhiya",
        }
    ]
    pq.write_table(pa.Table.from_pylist(frame), raw / "frame.parquet")
    winner = {
        "Dist": 33,
        "BlockID": 1,
        "Post": "Mukhiya",
        "PanchayatNo": 12,
        "CandidateName": "Synthetic",
        "Age": 27,
        "Category": "candidate category",
        "ReservationStatus": "reported category",
        "ReservationFor": "female",
    }
    reservation = {
        "Dist": 33,
        "BlockID": 1,
        "Post": "Mukhiya",
        "PanchayatNo": 12,
        "Reservation": "seat category",
    }
    archive(raw / "winners/d33_b1_p3.jsonl.gz", [winner])
    archive(raw / "reservations/d33_b1_p3.jsonl.gz", [reservation])
    parse(raw, out)
    row = pq.read_table(out / "winners.parquet").to_pylist()[0]
    assert row["year"] is None
    assert row["candidate_age"] == 27
    assert row["candidate_category"] == "candidate category"
    assert row["reservation_status_reported"] == "reported category"
    assert row["seat_reservation"] is None
    assert json.loads(row["raw_cell"]) == winner
    winner["Dist"] = 34
    archive(raw / "winners/d33_b1_p3.jsonl.gz", [winner])
    with pytest.raises(ValueError, match="geography"):
        parse(raw, out)


def test_age_type_and_retry_after():
    assert attributes({})["candidate_age"] is None
    with pytest.raises(ValueError, match="age"):
        attributes({"Age": "twenty"})
    assert retry_after("120") == 120


def test_2021_requires_explicit_phase(tmp_path):
    raw = tmp_path / "raw"
    (raw / "2021").mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist([{"district_id": 33, "block_id": 1, "panchayat_id": 12}]),
        raw / "2021/frame.parquet",
    )
    row = {
        "Dist": 33,
        "BlockID": 1,
        "PanchayatNo": 12,
        "OrderBy": 1,
        "CandidateName": "Synthetic",
        "IsWin": True,
        "TotalVote": 7,
    }
    path = raw / "2021/results/d33_b1_p12.jsonl.gz"
    archive(path, [row], phase="2021_1")
    sec_2021.parse(raw, tmp_path / "out")
    result = pq.read_table(tmp_path / "out/mukhiya_2021.parquet").to_pylist()[0]
    assert result["year"] == 2021 and result["elected"] is True
    assert result["candidate_age"] is None
    archive(path, [row], phase="2026_1")
    with pytest.raises(ValueError, match="phase"):
        sec_2021.parse(raw, tmp_path / "out")

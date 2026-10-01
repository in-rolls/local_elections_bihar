"""Synthetic source contracts; no requests to the live SEC service."""

import base64
import gzip
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.shared.portal import completed, decode_records, retry_after
from scripts.year2021 import collect_mukhiya as sec_2021


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


def test_retry_after():
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


def test_cached_request_accepts_equivalent_url_parameter_types(tmp_path):
    from scripts.shared.portal import fetch

    path = tmp_path / "cached.jsonl.gz"
    event = {
        "ok": True,
        "page": "Result",
        "params": {"panchayatId": "123"},
        "body_base64": base64.b64encode(b"[]").decode(),
    }
    with gzip.open(path, "wt") as stream:
        stream.write(json.dumps(event) + "\n" + json.dumps({"done": True}) + "\n")
    assert fetch(tmp_path, "cached", "Result", {"panchayatId": 123}) == b"[]"
    with pytest.raises(ValueError, match="Checkpoint request"):
        fetch(tmp_path, "cached", "Result", {"panchayatId": 124})

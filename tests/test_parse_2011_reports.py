"""District extraction, conservative reservation mapping and dated corroboration."""

import collections
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

from local_elections_bihar.year2011 import parse_gaya as p
from local_elections_bihar.year2011.parse_reports import release_records, reservation

OUT = Path("data/2011/mukhiya_reports")


@pytest.mark.parametrize(
    ("raw", "category", "women"),
    [
        ("अनारक्षित", "unreserved", None),
        ("अना0 अन् य", "unreserved", False),
        ("अनु0 महिला", None, True),
        ("अनु0 जाति महिला", "SC", True),
        ("अनुसूचित जनजाति अन्य", "ST", False),
        ("पिछडा वर्ग", "BC", None),
        ("अति पिछडा वर्ग", "EBC", None),
        ("आरक्षित", None, None),
        (None, None, None),
        ("अनारक्षित महिला अन्य", None, None),
    ],
)
def test_reservation_preserves_unknowns(raw, category, women):
    assert reservation(raw) == (category, women)


def test_bad_cell_is_null_with_receipt_or_fails_in_strict_mode(monkeypatch):
    table = SimpleNamespace(
        bbox=(0, 0, 90, 20),
        rows=[SimpleNamespace(cells=[(0, 0, 30, 10), (30, 0, 90, 10)])],
    )
    page = SimpleNamespace(
        page_number=3,
        edges=[{"top": y, "orientation": "h", "width": 90} for y in (0, 10, 20)],
        chars=[{"text": "1", "x0": 5, "x1": 7, "top": 15, "bottom": 17}],
    )

    def decode(_, box):
        if box[0] == 0:
            return "1"
        raise ValueError("Unresolved reph")

    monkeypatch.setattr(p, "cell_text", decode)
    with pytest.raises(ValueError, match="Unresolved reph"):
        list(p.grid_rows(page, table, 2))
    issues = []
    assert next(p.grid_rows(page, table, 2, decode_issues=issues))[1] == ["1", None]
    assert issues[0]["source_page"] == 3
    assert issues[0]["source_serial"] == 1
    assert issues[0]["column"] == 1
    assert json.loads(issues[0]["source_box"]) == [30, 10, 90, 20]


def test_district_records_and_visual_transcription():
    rows = pq.read_table(OUT / "winner_records.parquet").to_pylist()
    assert len(rows) == 3973
    assert len({r["record_id"] for r in rows}) == 3973
    assert len({r["district_raw"] for r in rows}) == 23
    assert {r["election_year"] for r in rows} == {2011}
    assert {r["year_basis"] for r in rows} == {p.YEAR_ASSIGNMENT["year_basis"]}
    assert not any(r["missing_block"] for r in rows)
    assert sum(r["decode_issue_count"] for r in rows) == 5
    serials = collections.defaultdict(list)
    for row in rows:
        assert all(
            (row[key] or "").strip()
            for key in ["district_raw", "block_raw", "panchayat_raw", "candidate_name"]
        )
        serials[row["source_file"]].append(row["source_serial"])
        assert bool(row["block_raw"]) != row["missing_block"]
        if row["missing_block"]:
            assert row["seat_label_repeated"] is None
            assert row["name_within_block_repeated"] is None
    for values in serials.values():
        assert values == sorted(set(values))
    indexed = {(r["district_raw"], str(r["source_serial"])): r for r in rows}
    assert not any(r["duplicate_of_record_id"] for r in rows)
    with Path("tests/fixtures/2011/district_visual_review.csv").open() as stream:
        reviewed = list(csv.DictReader(stream))
    assert len(reviewed) == 16
    for expected in reviewed:
        if (expected["district_raw"], expected["source_serial"]) == ("BHOJPUR", "16"):
            assert (expected["district_raw"], expected["source_serial"]) not in indexed
            continue
        actual = indexed[(expected["district_raw"], expected["source_serial"])]
        for field, value in expected.items():
            assert str(actual[field]) == value, (expected["source_serial"], field)
    assert indexed[("BEGUSARAI", "43")]["reservation_raw"] is None
    runners = pq.read_table(
        "data/2011/gaya_mukhiya/runner_up_records.parquet"
    ).to_pylist()
    by_id = {r["record_id"]: r for r in rows}
    for runner in runners:
        winner = by_id[runner["seat_source_record_id"]]
        assert winner["panchayat_raw"] == runner["panchayat_raw"]
        assert winner["source_sha256"] == runner["seat_source_sha256"]
    manifest = json.loads((OUT / "MANIFEST.json").read_text())["validation"]
    assert manifest["source_records"] == len(rows) + 47 + 300
    assert manifest["excluded_missing_location_or_name"] == 47
    assert manifest["excluded_exact_repeats"] == 300
    with (OUT / "issues.csv").open() as stream:
        excluded = [
            row
            for row in csv.DictReader(stream)
            if row["kind"] == "excluded_missing_location_or_name"
        ]
    assert len(excluded) == 47
    assert any(
        r["source_file"] == "winners/BHOJPUR/BHOJPUR_GPM.pdf"
        and r["source_serial"] == "16"
        and r["field"] == "panchayat_raw"
        for r in excluded
    )


def test_output_receipts_and_dated_contest():
    court = Path("data/2011/khajuria_judgment")
    for directory in [OUT, Path("data/2011/gaya_mukhiya")]:
        manifest = json.loads((directory / "MANIFEST.json").read_text())
        assignment = manifest["year_assignment"]
        evidence = Path(assignment["path"])
        assert hashlib.sha256(evidence.read_bytes()).hexdigest() == assignment["sha256"]
        assert assignment["election_year"] == 2011
    for directory in [OUT, court]:
        metadata = json.loads((directory / "MANIFEST.json").read_text())
        for name, info in metadata["files"].items():
            digest = info if isinstance(info, str) else info["sha256"]
            assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    with (court / "candidates.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert [r["source_table_label"] for r in rows] == list("abcdefghijk")
    assert [int(r["votes"]) for r in rows] == [
        45,
        397,
        26,
        79,
        200,
        862,
        48,
        28,
        369,
        52,
        1268,
    ]
    assert {r["election_year"] for r in rows} == {"2011"}
    assert [
        r["source_table_label"] for r in rows if r["initial_outcome"] == "elected"
    ] == ["k"]
    receipt = json.loads((court / "MANIFEST.json").read_text())
    match = receipt["matched_report"]
    report = pq.read_table(OUT / "winner_records.parquet").to_pylist()
    winner = next(r for r in report if r["record_id"] == match["record_id"])
    assert all(winner[k] == v for k, v in match.items())
    assert winner["election_year"] == 2011


def test_release_requires_location_and_removes_only_exact_repeats():
    row = {
        "record_id": "first",
        "district_raw": "Gaya",
        "block_raw": "Amas",
        "panchayat_raw": "कलवन",
        "candidate_name": "विगनी देवी",
        "source_file": "original.pdf",
        "source_serial": 1,
        "source_page": 1,
        "source_box": "[0,0,1,1]",
        "duplicate_of_record_id": None,
    }
    repeat = {**row, "record_id": "repeat", "duplicate_of_record_id": "first"}
    different = {**row, "record_id": "different", "candidate_name": "different"}
    missing = {**row, "record_id": "missing", "block_raw": ""}
    kept, excluded, duplicates = release_records([row, repeat, different, missing])
    assert [r["record_id"] for r in kept] == ["first", "different"]
    assert all(r["seat_label_repeated"] for r in kept)
    assert duplicates == 1
    assert len(excluded) == 1
    assert excluded[0]["field"] == "block_raw"

import json
import shutil

import pyarrow.parquet as pq
import pytest

from local_elections_bihar.urban import parse_patna as patna


def test_complete_offline_build_and_source_conflicts(tmp_path):
    patna.build(patna.RAW, patna.REFERENCE, patna.TCPD, tmp_path)
    winners = pq.read_table(tmp_path / "winners.parquet")
    assert winners.num_rows == 150
    assert winners.equals(pq.read_table(patna.RELEASE / "winners.parquet"))
    rows = winners.to_pylist()
    assert len({(r["election_year"], r["ward_id"]) for r in rows}) == 150
    assert all(r["is_woman"] is not None for r in rows)
    flagged = [r for r in rows if r["sex_reservation_conflict"]]
    assert [(r["election_year"], r["ward_id"]) for r in flagged] == [(2017, "26")]
    assert flagged[0]["sex_recorded"] == "पुरुष"
    assert not flagged[0]["is_woman"]
    conflicts = json.loads((tmp_path / "source_conflicts.json").read_text())
    assert {r["ward_id"] for r in conflicts["reservation_conflicts"]} == {"32", "35"}
    later = [r for r in rows if r["election_year"] == 2022]
    assert all(r["education_reported"] is None for r in later)
    assert all("not_election_age" in r["age_reference"] for r in later)
    candidates = pq.read_table(tmp_path / "candidates_2017.parquet")
    assert candidates.num_rows == 1008
    links = pq.read_table(tmp_path / "ward_transitions.parquet").to_pylist()
    assert len(links) == 75
    assert all(r["category_from"] == r["category_to"] for r in links)
    assert all(r["women_reserved_from"] == r["women_reserved_to"] for r in links)
    assert not any(r["boundary_equivalence_verified"] for r in links)
    assert not any(r["post_quota_open_transition"] for r in links)


def test_changed_source_rejected_even_after_prior_hash(tmp_path):
    raw = tmp_path / "raw"
    shutil.copytree(patna.RAW, raw)
    source = raw / "winners_2017_page1.html"
    patna.sha(source)
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Source checksum changed"):
        patna.build(raw, patna.REFERENCE, patna.TCPD, tmp_path / "release")


def test_changed_transcription_rejected(tmp_path):
    reference = tmp_path / "reference"
    shutil.copytree(patna.REFERENCE, reference)
    source = reference / "reservations_2017_transcription.csv"
    source.write_text(source.read_text().replace("1,SC,0,", "1,SC,1,", 1))
    with pytest.raises(ValueError, match="transcription checksum changed"):
        patna.build(patna.RAW, reference, patna.TCPD, tmp_path / "release")


def test_duplicate_frame_rejected_and_sex_not_inferred():
    rows, _ = patna.parse_2017(patna.RAW, patna.REFERENCE)
    with pytest.raises(ValueError, match="Incomplete or duplicated"):
        patna.validate_winners([*rows[:-1], rows[0]], 2017)
    with pytest.raises(ValueError, match="Unrecognized recorded sex"):
        patna.row(2017, "1", "Name", "", patna.RAW / "winners_2017_page1.html", 1, {})
    assert [patna.ward(n) for n in [73, 74, 75]] == ["22A", "22B", "22C"]

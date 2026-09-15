"""Synthetic contracts for the 2021 release build; no live requests."""

import base64
import gzip
import io
import json
import tarfile

import build_2021 as b
import polars as pl
import pytest
from pandera.errors import SchemaErrors
from schemas_2021 import TABLES, polars_schema

URL = "https://sec25.bihar.gov.in/x"


def ledger(records, phase=None):
    event = {
        "ok": True,
        "url": URL,
        "fetched_at": "2026-09-13T00:00:00+00:00",
        "params": {"phase": phase},
        "body_base64": base64.b64encode(json.dumps(records).encode()).decode(),
    }
    lines = json.dumps(event) + "\n" + json.dumps({"done": True}) + "\n"
    return gzip.compress(lines.encode())


def archive(tmp_path, members):
    path = tmp_path / "a.tar"
    with tarfile.open(path, "w") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return b.Responses([path])


def seat(post=5, seat_no=8):
    return {
        "post_id": post,
        "district_id": 2,
        "block_id": 11,
        "panchayat_id": None,
        "seat_no": seat_no,
        "unit_id": f"d2_b11_s{seat_no}",
        "district": "D",
        "block": "B",
        "panchayat": None,
    }


def candidate(serial, name, gender="पुरुष "):
    return {
        "PostId": 5,
        "OrderBy": serial,
        "CandidateName": name,
        "GaurdianName": "G",
        "Age": 40,
        "Gender": gender,
        "CandidateAddress": "A",
        "CandidatePhoto": "https://x/p.jpg",
        "CandidateDoc": "https://x/d.pdf",
        "SymbolName": "S",
        "SymbolUrl": "1.png",
    }


def result(serial, name, panchayat, votes, won):
    return {
        "SlNo": serial * 100 + panchayat,
        "PostName": "P",
        "Dist": 2,
        "DistrictName": "D",
        "BlockID": 11,
        "BlockName": "B",
        "PanchayatNo": panchayat,
        "PanchayatName": "N",
        "WardNo": 8,
        "OrderBy": serial,
        "CandidateName": name + (" (विजेता)" if won else ""),
        "TotalVote": votes,
        "IsWin": won,
    }


def build(tmp_path, candidates, results):
    root = "2021/offices/p5"
    responses = archive(
        tmp_path,
        {
            f"{root}/phases/d2_b11_s8.jsonl.gz": ledger([{"i": "2021_1", "n": "2021"}]),
            f"{root}/candidates/d2_b11_s8.jsonl.gz": ledger(candidates, "2021_1"),
            f"{root}/results/d2_b11_s8.jsonl.gz": ledger(results, "2021_1"),
            f"{root}/._candidates.jsonl.gz": b"\x00\x05\x16\x07",
        },
    )
    return b.build_post([seat()], responses)


def validate(name, rows):
    schema = polars_schema(TABLES[name])
    frame = pl.DataFrame(
        [{c: r.get(c) for c in schema} for r in rows], schema=schema, orient="row"
    )
    return TABLES[name].validate(frame, lazy=True)


def test_partial_flag_result_only_candidate_and_valid_tables(tmp_path):
    # Mirrors samiti d2_b11_s8: IsWin set on one of the winner's panchayat rows,
    # and a candidate present only in the results.
    seats, candidates, results, winners = build(
        tmp_path,
        [candidate(1, "अजय कुमार"), candidate(2, "सन्नी कुमार")],
        [
            result(1, "अजय कुमार", 182, 699, False),
            result(1, "अजय कुमार", 213, 15, False),
            result(2, "सन्नी कुमार", 182, 223, False),
            result(2, "सन्नी कुमार", 213, 517, True),
            result(3, "सोनी देवी", 182, 5, False),
            result(3, "सोनी देवी", 213, 6, False),
        ],
    )
    assert seats[0]["winner_flag_partial"] is True
    assert seats[0]["result_only_candidates"] == 1
    unlisted = [c for c in candidates if not c["in_candidate_list"]]
    assert [(c["candidate_name"], c["votes"]) for c in unlisted] == [("सोनी देवी", 11)]
    assert winners[0]["votes"] == 740 and winners[0]["candidate_serial"] == 2
    for name, rows in [
        ("seats", seats),
        ("candidates", candidates),
        ("result_rows", results),
        ("winners", winners),
    ]:
        validate(name, rows)


def test_unknown_source_field_stops_the_build(tmp_path):
    row = candidate(1, "अजय कुमार") | {"NewField": "x"}
    with pytest.raises(ValueError, match="Unmapped source fields"):
        build(tmp_path, [row], [])


def test_unknown_gender_and_non_url_links_fail(tmp_path):
    with pytest.raises(ValueError, match="Unknown gender"):
        build(tmp_path, [candidate(1, "अजय", gender="M")], [])
    _, candidates, _, _ = build(tmp_path, [candidate(1, "अजय")], [])
    candidates[0]["photo_url"] = "01-Nov-2023"
    with pytest.raises(SchemaErrors):
        validate("candidates", candidates)


def test_result_for_other_seat_is_rejected(tmp_path):
    other = result(1, "अजय", 182, 5, True) | {"WardNo": 9}
    with pytest.raises(ValueError, match="outside requested seat"):
        build(tmp_path, [candidate(1, "अजय")], [other])


def test_vacant_placeholder_fields_are_not_a_person(tmp_path):
    row = {
        "Dist": 2,
        "BlockID": 11,
        "PanchayatNo": 20110182,
        "WardNo": 6,
        "District": "D",
        "Block": "B",
        "Panchayat": "N",
        "Post": "P",
        "ReservationFor": "महिला",
        "CandidateName": None,
        "GuardianName": None,
        "MobileNo": "9999999999",
        "Gender": "महिला",
        "Age": 55,
        "Address": None,
        "Category": "C",
        "ReservationStatus": None,
        "CandidatePhotos": "01-Nov-2023",
        "Affidavit": "ok",
    }
    responses = archive(
        tmp_path, {"current/winners/p1/d2_b11_p20110182.jsonl.gz": ledger([row])}
    )
    frame = [seat(1, 6) | {"panchayat_id": 20110182, "unit_id": "d2_b11_p20110182_w6"}]
    winner = b.build_current(responses, {}, frame)["winners"][0]
    assert winner["vacant_placeholder"] is True
    assert winner["candidate_age"] is None and winner.get("photo_url") is None
    assert winner["placeholder_date"] == "01-Nov-2023"
    assert "MobileNo" not in winner
    validate("current_winners", [winner])


def test_results_without_serial_are_not_pooled(tmp_path):
    # 16,113 ward-member result rows have OrderBy null.
    rows = [
        result(1, "अली अकबर", 182, 10, False) | {"OrderBy": None},
        result(2, "उमेश कुमार सिंह", 182, 63, True) | {"OrderBy": None},
    ]
    _, candidates, results, winners = build(
        tmp_path, [candidate(1, "उमेश कुमार सिंह"), candidate(2, "अली अकबर")], rows
    )
    votes = {c["candidate_name"]: c["votes"] for c in candidates}
    assert votes == {"उमेश कुमार सिंह": 63, "अली अकबर": 10}
    assert [r["result_serial"] for r in results] == [None, None]
    assert winners[0]["candidate_serial"] == 1 and winners[0]["votes"] == 63
    validate("candidates", candidates)
    validate("result_rows", results)

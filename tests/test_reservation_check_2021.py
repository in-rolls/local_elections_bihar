import copy
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from check_reservations_2021 import INPUTS, audit, category
from release_2021 import sha


@pytest.fixture(scope="module")
def sources():
    return {name: pq.read_table(path).to_pylist() for name, path in INPUTS.items()}


def run(sources):
    return audit(
        **sources,
        official={"total": 8067, "sc": 1338, "st": 90, "bc": 1374, "women": 3583},
    )


def test_real_source_disagreements_are_preserved(sources):
    checks, flagged = run(sources)
    expected = json.loads(
        Path("data/fin/reservation_check_2021/validation.json").read_text()
    )
    assert checks == expected
    assert checks["current_minus_official"] == {
        "total": 0,
        "sc": 1,
        "st": 0,
        "bc": -1,
        "women": 0,
    }
    assert len(flagged) == 35
    assert checks["flagged_winners_current_gender"] == {"पुरुष": 4, "महिला": 31}
    assert all(r["gender_2021"].strip() == "पुरुष" for r in flagged)


def test_seat_reservation_does_not_follow_winner_gender():
    assert category("अनारक्षित  (अन्य)") == ("open", False)
    assert category("अनारक्षित  (महिला)") == ("open", True)
    with pytest.raises(ValueError, match="Unknown seat reservation"):
        category("महिला")


def test_duplicate_and_missing_geographic_keys_fail(sources):
    duplicate = {**sources, "reservations": sources["reservations"] * 2}
    with pytest.raises(ValueError, match="Duplicate"):
        run(duplicate)
    missing = {**sources, "reservations": sources["reservations"][1:]}
    with pytest.raises(ValueError, match="lack a reservation key"):
        run(missing)


def test_current_winner_disagreement_does_not_recode_2021(sources):
    altered = copy.deepcopy(sources)
    checks, flagged = run(altered)
    key = tuple(flagged[0][f] for f in ["district_id", "block_id", "panchayat_id"])
    for r in altered["current_winners"]:
        if tuple(int(r[f]) for f in ["district_id", "block_id", "panchayat_id"]) == key:
            r["candidate_gender"] = "अन्य"
    changed, rows = run(altered)
    assert changed["winners"] == checks["winners"]
    assert [r["gender_2021"] for r in rows] == [r["gender_2021"] for r in flagged]


def test_published_audit_checksums_and_provenance():
    root = Path("data/fin/reservation_check_2021")
    for line in (root / "CHECKSUMS").read_text().splitlines():
        digest, name = line.split()
        assert sha(root / name) == digest
    manifest = json.loads((root / "MANIFEST.json").read_text())
    for path, digest in (manifest["inputs"] | manifest["receipts"]).items():
        assert sha(Path(path)) == digest
    assert sha(Path("scripts/check_reservations_2021.py")) == manifest["parser_sha256"]

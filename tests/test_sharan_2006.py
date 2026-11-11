"""Reading M. R. Sharan's 2006 gram panchayat head reservations."""

import collections

import pytest

from local_elections_bihar.parse import sharan_2006


@pytest.fixture(scope="module")
def rows():
    return sharan_2006.rows()


def test_flag_totals_are_the_files(rows):
    raw = sharan_2006.frame()
    assert len(rows) == len(raw) == 8262
    caste = collections.Counter(r["reserved_caste"] for r in rows)
    assert caste == {"NONE": 5420, "SC": 1361, "ST": 68, "EBC": 1413}
    for flag, value in sharan_2006.FLAGS.items():
        assert raw[flag].sum() == caste[value]
    assert sum(r["reserved_woman"] for r in rows) == 3692
    assert raw[sharan_2006.WOMAN].sum() == 3692


def test_identifier_and_place_are_unique(rows):
    assert len({r["ugp"] for r in rows}) == len(rows)
    places = {(r["district"], r["block"], r["gram_panchayat"]) for r in rows}
    assert len(places) == len(rows)
    assert len({r["district"] for r in rows}) == 38


def test_rows_keep_the_files_order(rows):
    assert [r["source_row"] for r in rows] == list(range(1, len(rows) + 1))
    assert rows[0] | {"source_path": None} == {
        "ugp": 1,
        "district": "ARARIA",
        "block": "ARARIA",
        "gram_panchayat": "ARARIA BASTI",
        "gram_panchayat_raw": "ARARIA BASTI",
        "reserved_caste": "NONE",
        "reserved_woman": 1,
        "source_path": None,
        "source_row": 1,
    }


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("\u00c2\u00a0SAKRI KHURD", "SAKRI KHURD"),
        ("BASO PATTI      ( EAST)", "BASO PATTI ( EAST)"),
        # punctuation is the file's and stays
        ("CHILHAR;UWA", "CHILHAR;UWA"),
    ],
)
def test_clean_removes_only_spacing(raw, cleaned):
    assert sharan_2006.clean(raw) == cleaned


def test_mis_encoded_names_are_repaired_and_kept(rows):
    odd = [r for r in rows if "\u00a0" in r["gram_panchayat_raw"]]
    assert sorted(r["gram_panchayat"] for r in odd) == [
        "KHAJURI",
        "KOCHAHASA",
        "SAKRI KHURD",
    ]
    assert all(r["gram_panchayat"].isascii() for r in rows)


def test_changed_coding_stops_the_read(monkeypatch):
    monkeypatch.setitem(sharan_2006.LABELS, "ebc_reserved_2006", "something else")
    with pytest.raises(SystemExit, match="labels have changed"):
        sharan_2006.frame()

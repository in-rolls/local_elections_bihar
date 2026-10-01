"""Extraction regressions and visually transcribed Gaya source checks."""

import csv
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

from scripts.year2011 import parse_gaya as p
from scripts.year2011.hindi import cell_text, kruti_text, logical_text

PILOT = Path("data/2011/gaya_mukhiya")
REVIEW = Path("tests/fixtures/2011/gaya_visual_review.csv")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("िवगनी देवी", "विगनी देवी"),
        ("िसंह", "सिंह"),
        ("धम\ue000", "धर्म"),
        ("िनम\ue000ला", "निर्मला"),
    ],
)
def test_visual_order(raw, expected):
    assert logical_text(raw) == expected


def test_unknown_reph_is_rejected():
    with pytest.raises(ValueError, match="Unresolved reph"):
        logical_text("\ue000")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pkS/kjh", "चौधरी"),
        ("eqf[k;k", "मुखिया"),
        ("fcgkj", "बिहार"),
    ],
)
def test_kruti_known_words(raw, expected):
    assert kruti_text(raw) == expected


def char(text, x, y=15):
    return {"text": text, "x0": x, "x1": x + 2, "top": y, "bottom": y + 2}


def test_drawing_order_preserves_prebase_mark():
    page = SimpleNamespace(chars=[char("ि", 8), char("क", 3)])
    assert cell_text(page, (0, 0, 20, 30)) == "कि"


def test_last_row_with_missing_vertical_rule():
    # The detector merges the last two cells; header columns still recover them.
    table = SimpleNamespace(
        bbox=(0, 0, 90, 30),
        rows=[
            SimpleNamespace(cells=[(0, 0, 30, 10), (30, 0, 60, 10), (60, 0, 90, 10)]),
            SimpleNamespace(
                cells=[(0, 10, 30, 20), (30, 10, 60, 20), (60, 10, 90, 20)]
            ),
            SimpleNamespace(cells=[(0, 20, 60, 30), None, (60, 20, 90, 30)]),
        ],
    )
    page = SimpleNamespace(
        page_number=1,
        edges=[{"top": y, "orientation": "h", "width": 90} for y in (0, 10, 20, 30)],
        chars=[
            char("1", 5),
            char("क", 35),
            char("9", 65),
            char("2", 5, 25),
            char("ख", 35, 25),
            char("8", 65, 25),
        ],
    )
    rows = list(p.grid_rows(page, table, 3))
    assert [r[1] for r in rows] == [["1", "क", "9"], ["2", "ख", "8"]]


def test_summary_carries_block_header_across_page(monkeypatch):
    header = {**char("Tankuppa", 80, 777), "fontname": "AAAA+Arial-Bold"}
    numeric = {**char("120", 233, 793), "fontname": "AAAA+Arial-Bold"}
    page1 = SimpleNamespace(chars=[header, numeric], find_tables=lambda: [])
    cells = ["1", "मुखिया", "5", "5", "10", "50%"]
    table = SimpleNamespace(
        bbox=(50, 110, 550, 150), rows=[SimpleNamespace(cells=cells)]
    )
    page2 = SimpleNamespace(chars=[], find_tables=lambda: [table])
    monkeypatch.setattr(
        p, "decoded_pdf", lambda _: nullcontext(SimpleNamespace(pages=[page1, page2]))
    )
    monkeypatch.setattr(p, "cell_text", lambda _, cell: cell)
    page2.page_number = 2
    assert p.summaries(Path("/unused")) == [
        {"block_raw": "Tankuppa", "female": 5, "male": 5, "total": 10, "source_page": 2}
    ]


def check_review(directory):
    rows = {
        r["source_serial"]: r
        for r in pq.read_table(directory / "pdf_winner_records.parquet").to_pylist()
    }
    with REVIEW.open() as f:
        expected = list(csv.DictReader(f))
    assert len(expected) == 32
    for sample in expected:
        actual = rows[int(sample["source_serial"])]
        for field, value in sample.items():
            assert str(actual[field]) == value, (sample["source_serial"], field)
    assert rows[232]["gender"] == "male"  # Retain the printed label.
    assert rows[129]["age"] is None
    assert rows[129]["age_raw"] == "1980"


def test_published_transcription_and_years():
    check_review(PILOT)
    for filename, count, year in [
        ("pdf_winner_records", 338, 2011),
        ("spreadsheet_winner_records", 330, 2011),
        ("runner_up_records", 337, 2011),
    ]:
        table = pq.read_table(PILOT / (filename + ".parquet"))
        rows = table.to_pylist()
        assert len(rows) == count
        assert {r["election_year"] for r in rows} == {year}
        assert str(table.schema.field("election_year").type) == "int64"
        assert len({r["record_id"] for r in rows}) == count
        assert all(len(r["source_sha256"]) == 64 for r in rows)
        assert all(
            r[field].strip()
            for r in rows
            for field in ["district", "block", "panchayat_raw", "candidate_name"]
        )


@pytest.mark.skipif(
    not (p.ROOT / p.SOURCES["winners"]).exists(),
    reason="Original Gaya sources are on the external drive",
)
def test_local_source_extraction(tmp_path):
    p.run(p.ROOT, tmp_path)
    check_review(tmp_path)
    report = json.loads((tmp_path / "MANIFEST.json").read_text())["validation"]
    assert report["summary_total"] == report["winner_rows"] == 338
    assert report["coverage_all_blocks_match"]
    assert report["alternate_identity_matches"] == 338
    assert report["spreadsheet_rows"] == 331
    assert report["runner_name_rows"] == 338
    assert report["published_spreadsheet_winners"] == 330
    assert report["published_runners"] == 337
    assert report["runner_seat_linkage"]["corroborating_gp_headings"] == 25


def paired_records():
    runners = [
        {
            "source_serial": 1,
            "block_raw": "Amas",
            "reservation_raw": "महिला सामान्य",
            "block_first_panchayat_heading": "कलवन",
        },
        {
            "source_serial": 2,
            "block_raw": "Amas",
            "reservation_raw": "सामान्य महिला",
            "block_first_panchayat_heading": None,
        },
    ]
    winners = [
        {
            "serial": r["source_serial"],
            "block_raw": r["block_raw"],
            "reservation_raw": r["reservation_raw"],
            "panchayat_raw": gp,
            "source_file": "winners.pdf",
            "source_page": 1,
        }
        for r, gp in zip(runners, ["कलवन", "अकौना"], strict=True)
    ]
    return runners, winners


def test_runner_link_uses_companion_gp_not_group_heading():
    runners, winners = paired_records()
    linked, report = p.link_runner_seats(runners, list(reversed(winners)))
    assert [r["panchayat_raw"] for r in linked] == ["कलवन", "अकौना"]
    assert {r["seat_link_basis"] for r in linked} == {"inferred_paired_report_order"}
    assert report["aligned_source_rows"] == 2
    assert report["corroborating_gp_headings"] == 1


@pytest.mark.parametrize("field", ["block_raw", "reservation_raw", "panchayat_raw"])
def test_runner_link_rejects_disagreement(field):
    runners, winners = paired_records()
    winners[0][field] = "different"
    with pytest.raises(ValueError, match=r"alignment changed|GP heading disagrees"):
        p.link_runner_seats(runners, winners)


@pytest.mark.parametrize("defect", ["missing", "duplicate"])
def test_runner_link_rejects_incomplete_or_duplicate_serials(defect):
    runners, winners = paired_records()
    winners = winners[:-1] if defect == "missing" else winners + winners[:1]
    with pytest.raises(ValueError, match="one-to-one"):
        p.link_runner_seats(runners, winners)


@pytest.mark.parametrize(
    "missing", ["district", "block", "panchayat_raw", "candidate_name"]
)
def test_minimum_record_requires_location_and_person(missing):
    complete = {
        "record_id": "complete",
        "district": "Gaya",
        "block": "Amas",
        "panchayat_raw": "कलवन",
        "candidate_name": "अर्चना यादवेंदु",
    }
    incomplete = {**complete, "record_id": "incomplete", missing: "  "}
    kept, excluded = p.minimum_records([complete, incomplete])
    assert kept == [complete]
    assert excluded == [{"record_id": "incomplete", "missing": [missing]}]

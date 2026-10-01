"""Extraction regressions and visually transcribed Gaya source checks."""

import csv
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import parse_2011 as p
import pyarrow.parquet as pq
import pytest
from hindi_2011 import cell_text, kruti_text, logical_text

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
        ("spreadsheet_winner_records", 331, 2011),
        ("runner_name_records", 338, 2011),
    ]:
        table = pq.read_table(PILOT / (filename + ".parquet"))
        rows = table.to_pylist()
        assert len(rows) == count
        assert {r["election_year"] for r in rows} == {year}
        assert str(table.schema.field("election_year").type) == "int64"
        assert len({r["record_id"] for r in rows}) == count
        assert all(len(r["source_sha256"]) == 64 for r in rows)


@pytest.mark.skipif(
    not (p.ROOT / p.SOURCES["winners"]).exists(),
    reason="Original Gaya sources are on the external drive",
)
def test_local_source_extraction(tmp_path):
    p.run(p.ROOT, tmp_path)
    check_review(tmp_path)
    report = json.loads((tmp_path / "validation.json").read_text())
    assert report["summary_total"] == report["winner_rows"] == 338
    assert report["coverage_all_blocks_match"]
    assert report["alternate_identity_matches"] == 338
    assert report["spreadsheet_rows"] == 331
    assert report["runner_name_rows"] == 338

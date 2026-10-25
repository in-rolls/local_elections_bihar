"""The 2001 elected-mukhiya lists, read from the SEC's Akruti PDFs."""

import polars as pl
import pytest

from local_elections_bihar.parse import mukhiya_2001
from local_elections_bihar.parse.schema_2001 import TABLES
from local_elections_bihar.shared.schema import polars_schema


@pytest.fixture(scope="module")
def table():
    """Parsed fresh from the PDFs, not read from the release."""
    schema = polars_schema(TABLES["mukhiya_winners"])
    return pl.DataFrame(mukhiya_2001.build(), schema=schema, orient="row")


def row(table, district, block, serial):
    found = table.filter(
        (pl.col("district") == district)
        & (pl.col("block") == block)
        & (pl.col("serial") == serial)
    )
    assert found.height == 1, (district, block, serial, found.height)
    return found.row(0, named=True)


def test_every_division_district_and_block_is_named(table):
    assert table.height == 8426
    assert table["division"].null_count() == 0
    assert table["district"].null_count() == 0
    assert table["block"].null_count() == 0
    assert (table["gram_panchayat"] == "").sum() == 0
    # Koshi's file carries Bhagalpur division too, so all nine are present
    assert table["division"].str.replace("पुर्णियाँ", "पूर्णिया").n_unique() == 9


def test_a_row_with_its_own_honorific(table):
    got = row(table, "पटना", "पटना सदर", 1)
    assert got["gram_panchayat"] == "नकटा दियारा"
    assert (got["winner_honorific"], got["winner"]) == ("श्री", "विजय कुमार यादव")
    assert got["honorific_from_ditto"] is False


def test_a_ditto_mark_carries_the_honorific_down(table):
    got = row(table, "पटना", "पटना सदर", 2)
    assert got["winner"] == "श्याम नारायण राय"
    assert (got["winner_honorific"], got["honorific_from_ditto"]) == ("श्री", True)


def test_a_name_printed_in_its_own_cell(table):
    # Nalanda's lists set the panchayat name apart from its serial number
    got = row(table, "नालंदा", "बिहारशरीफ", 1)
    assert (got["gram_panchayat"], got["winner"]) == ("बियावानी", "संजय कुमार")


def test_a_district_named_on_the_line_below_its_heading(table):
    assert row(table, "नवादा", "नवादा", 1)["gram_panchayat"] == "खराँट"


def test_a_block_the_sec_printed_without_winners(table):
    kudra = table.filter(pl.col("block") == "कुदरा")
    assert kudra.height == 15
    assert kudra["winner"].null_count() == 15


def test_no_reservation_column(table):
    assert not [c for c in table.columns if c.startswith("reserved")]

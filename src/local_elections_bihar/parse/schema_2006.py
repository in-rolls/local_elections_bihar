"""Release contract for the 2006 tables: types, domains and meanings."""

import pandera.polars as pa
import polars as pl

from local_elections_bihar.shared.schema import field, nullable

OFFICES = [
    "ward_member",
    "panch",
    "mukhiya",
    "sarpanch",
    "panchayat_samiti_member",
    "zila_parishad_member",
]
CASTE = ["NONE", "SC", "ST", "BC"]
WINNER_CASTE = ["NONE", "SC", "ST", "BC", "EBC"]
WOMAN = [0, 1]

SOURCE = {
    "source_path": "Workbook the row was read from, relative to the repository.",
    "source_sheet": "Sheet name in that workbook.",
    "source_row": "One-based row number in that sheet.",
}


class Seat(pa.DataFrameModel):
    office: pl.Utf8 = field("Office of the seat.", isin=OFFICES)
    district: pl.Utf8 = field("District, from the workbook heading.")
    district_from_file: pl.Utf8 = field("District, from the workbook's file name.")
    block: pl.Utf8 = nullable("Block heading; null for zila parishad seats.")
    gram_panchayat: pl.Utf8 = nullable(
        "Gram panchayat (or its gram kachahari) heading or cell; null for samiti "
        "and zila parishad seats."
    )
    constituency_no: pl.Int32 = nullable(
        "Printed constituency number; for mukhiya and sarpanch, the serial."
    )
    constituency_name: pl.Utf8 = nullable(
        "Printed constituency name; null for mukhiya and sarpanch."
    )
    winner: pl.Utf8 = nullable("Decoded winner name as printed; null when vacant.")
    winner_raw: pl.Utf8 = nullable(
        "The winner cell's Kruti Dev bytes (workbooks only)."
    )
    vacant: pl.Boolean = field("The seat was printed vacant (रिक्त) or blank (----).")
    unopposed: pl.Boolean = nullable(
        "Returned unopposed (निर्विरोध); stated only by the result notices."
    )
    source_document: pl.Utf8 = field(
        "member_workbook: the SEC's member workbooks; profile_workbook: the SEC's "
        "mukhiya and sarpanch workbooks, which print no reservation; "
        "result_notice: a block's published result (प्रपत्र-23).",
        isin=["member_workbook", "profile_workbook", "result_notice"],
    )
    reserved_raw: pl.Utf8 = nullable(
        "Caste and woman cells as printed, joined by ' / '; null for seats from "
        "the profile workbooks, which state no reservation."
    )
    reserved_caste_local: pl.Utf8 = nullable("The printed caste cell.")
    reserved_caste: pl.Utf8 = nullable(
        "The seat's caste reservation read from reserved_caste_local; null when "
        "unstated, ambiguous or naming two categories.",
        isin=CASTE,
    )
    reserved_woman_raw: pl.Utf8 = nullable("The printed महिला/अन्य cell.")
    reserved_woman: pl.Int8 = nullable(
        "1 reserved for a woman (महिला), 0 not (अन्य); null when unstated.",
        isin=WOMAN,
    )
    source_path: pl.Utf8 = field(SOURCE["source_path"])
    source_sheet: pl.Utf8 = field(SOURCE["source_sheet"])
    source_row: pl.Int32 = field(SOURCE["source_row"])


class WinnerProfile(pa.DataFrameModel):
    office: pl.Utf8 = field("mukhiya or sarpanch.", isin=["mukhiya", "sarpanch"])
    district: pl.Utf8 = field("District, from the workbook heading.")
    district_from_file: pl.Utf8 = field("District, from the workbook's file name.")
    block: pl.Utf8 = nullable("Block heading.")
    serial: pl.Int32 = field("Serial printed within the block.")
    gram_panchayat: pl.Utf8 = nullable("Gram panchayat as printed.")
    winner: pl.Utf8 = nullable("Decoded winner name as printed, honorific included.")
    winner_raw: pl.Utf8 = nullable("The winner cell's Kruti Dev bytes.")
    winner_age: pl.Int16 = nullable("Age; null where blank or printed 0.")
    winner_address_raw: pl.Utf8 = nullable(
        "Address as printed, telephone numbers included."
    )
    winner_education_raw: pl.Utf8 = nullable("Education as printed.")
    winner_social_class_raw: pl.Utf8 = nullable(
        "Social standing as printed (उच्च/मध्यम/निम्न वर्ग)."
    )
    winner_caste_raw: pl.Utf8 = nullable(
        "The winner's own category as printed; some districts print a jati."
    )
    winner_caste: pl.Utf8 = nullable(
        "The winner's category read from winner_caste_raw: EBC is अत्यन्त पिछड़ा "
        "वर्ग; null for a jati, 'अन्य' or blank.",
        isin=WINNER_CASTE,
    )
    winner_income_inr: pl.Int64 = nullable("Annual income in rupees, when a number.")
    winner_income_raw: pl.Utf8 = nullable("Annual income as printed.")
    winner_occupation_raw: pl.Utf8 = nullable("Occupation as printed.")
    winner_sons: pl.Int16 = nullable("Number of sons.")
    winner_daughters: pl.Int16 = nullable("Number of daughters.")
    source_path: pl.Utf8 = field(SOURCE["source_path"])
    source_sheet: pl.Utf8 = field(SOURCE["source_sheet"])
    source_row: pl.Int32 = field(SOURCE["source_row"])


TABLES = {"seats": Seat, "winner_profiles": WinnerProfile}

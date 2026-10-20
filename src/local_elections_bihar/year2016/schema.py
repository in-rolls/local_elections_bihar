"""Release contract for the 2016 panchayat tables: types, domains, keys, meanings.

Built from re-collected pages of the SEC's archived 2016 results form. Each model
is the single source for a table's Arrow types, checks and dictionary entries.
"""

from typing import ClassVar

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
GENDERS = ["male", "female", "other"]
REMARKS = ["0", "Uncontested", "Vacant"]
SEAT_STATUS = ["results", "no_record"]
WINNER_NOTE = ["several_uncontested", "repeated_serial_differs", "tied_top_vote"]
WINNER_BASIS = ["uncontested", "lot", "top_vote"]
KEY = ["office", "district_code", "block_code", "panchayat_code", "unit_code"]


def keys():
    return {
        "office": field("Office, from the form's post list.", isin=OFFICES),
        "district_code": field("Form district code."),
        "block_code": nullable("Form block code; null for zila parishad."),
        "panchayat_code": nullable(
            "Form panchayat code; set for ward member and panch."
        ),
        "unit_code": field(
            "Form code of the seat: ward, panchayat, or territorial number."
        ),
    }


PROVENANCE = {
    "source_file": "Result ledger holding the saved page.",
    "source_event": "Zero-based position of the page in that ledger.",
    "fetched_at": "UTC time the page was retrieved.",
    "page_sha256": "SHA-256 of the saved page HTML.",
}


class Seat(pa.DataFrameModel):
    office: pl.Utf8 = keys()["office"]
    district_code: pl.Utf8 = keys()["district_code"]
    block_code: pl.Utf8 = keys()["block_code"]
    panchayat_code: pl.Utf8 = keys()["panchayat_code"]
    unit_code: pl.Utf8 = keys()["unit_code"]
    district: pl.Utf8 = field("District label from the form.")
    block: pl.Utf8 = nullable("Block label from the form.")
    panchayat: pl.Utf8 = nullable("Panchayat label (ward member and panch seats).")
    unit: pl.Utf8 = field("Seat label from the form dropdown.")
    code_repeated: pl.Boolean = field(
        "The form uses this code for more than one place in the same parent "
        "(Siwan, Ziradei panchayat 10); its page cannot be tied to one label."
    )
    seat_label: pl.Utf8 = nullable(
        "Territorial seat shown on the results page (lblPradesikForMukhiya)."
    )
    seat_reservation: pl.Utf8 = nullable(
        "Seat reservation shown on the results page; null on no-record pages and "
        "where the form shows its unset '--select--'."
    )
    status: pl.Utf8 = field(
        "results, or no_record when the form answers 'Record not Found'.",
        isin=SEAT_STATUS,
    )
    pages: pl.Int16 = field("Results-grid pages saved (20 candidates per page).", ge=1)
    candidate_rows: pl.Int32 = field("Candidate rows across all pages.", ge=0)
    winner_note: pl.Utf8 = nullable(
        "Why no winner is derived although rows exist: several distinct uncontested "
        "candidates, a serial repeated with a different person or vote count, or a "
        "top vote shared by two candidates with no lot mark.",
        isin=WINNER_NOTE,
    )

    class Config:
        strict = True
        unique: ClassVar[list[str]] = [*KEY, "panchayat", "unit"]


class Candidate(pa.DataFrameModel):
    office: pl.Utf8 = keys()["office"]
    district_code: pl.Utf8 = keys()["district_code"]
    block_code: pl.Utf8 = keys()["block_code"]
    panchayat_code: pl.Utf8 = keys()["panchayat_code"]
    unit_code: pl.Utf8 = keys()["unit_code"]
    row: pl.Int32 = field(
        "Position of the row in the seat's table, across pages.", ge=1
    )
    sr_no: pl.Int32 = nullable(
        "Sr No., the candidate serial in the seat; the source repeats some, starts "
        "some at 0 and leaves some blank.",
        ge=0,
    )
    sr_no_repeated: pl.Boolean = field("Another row of the seat has this Sr No.")
    candidate_name: pl.Utf8 = nullable("Candidate Name, verbatim.")
    father_husband_name: pl.Utf8 = nullable("Father/Hubs Name, verbatim.")
    gender_raw: pl.Utf8 = field("Gender, verbatim ('--' for vacant rows).")
    gender: pl.Utf8 = nullable(
        "Gender mapped to male/female/other (तृतीय लिंग); null for '--'.", isin=GENDERS
    )
    age: pl.Int32 = nullable(
        "Age as reported, implausibly low values included; null for '--', blank, "
        "or a number above 120 (see age_raw).",
        ge=0,
        le=120,
    )
    age_raw: pl.Utf8 = nullable("Age, verbatim.")
    category: pl.Utf8 = nullable("Category, verbatim; null for '--'.")
    education: pl.Utf8 = nullable("Educational Qualification, verbatim.")
    mobile_number: pl.Utf8 = nullable(
        "Mobile No., verbatim (text, leading zeros kept)."
    )
    address: pl.Utf8 = nullable("Address, verbatim.")
    email: pl.Utf8 = nullable("Email Id, verbatim.")
    votes: pl.Int64 = nullable(
        "Obtained Valid Vote; null for '--' (uncontested or vacant) or blank. "
        "For a tie drawn by lot ('136+1') the count before the plus.",
        ge=0,
    )
    votes_raw: pl.Utf8 = nullable("Obtained Valid Vote, verbatim.")
    won_by_lot: pl.Boolean = field(
        "The vote cell carries '+1': the form's mark for a tie decided by lot."
    )
    remarks: pl.Utf8 = field("Remarks: 0, Uncontested or Vacant.", isin=REMARKS)
    page: pl.Int16 = field("Results-grid page the row was on.", ge=1)
    source_file: pl.Utf8 = field(PROVENANCE["source_file"])
    source_event: pl.Int32 = field(PROVENANCE["source_event"], ge=0)
    fetched_at: pl.Utf8 = field(PROVENANCE["fetched_at"])
    page_sha256: pl.Utf8 = field(PROVENANCE["page_sha256"], str_length=64)

    class Config:
        strict = True
        unique: ClassVar[list[str]] = [*KEY, "row"]


class Winner(pa.DataFrameModel):
    office: pl.Utf8 = keys()["office"]
    district_code: pl.Utf8 = keys()["district_code"]
    block_code: pl.Utf8 = keys()["block_code"]
    panchayat_code: pl.Utf8 = keys()["panchayat_code"]
    unit_code: pl.Utf8 = keys()["unit_code"]
    sr_no: pl.Int32 = nullable("Winner's candidate serial.", ge=0)
    row: pl.Int32 = field("Winner's row in candidates.", ge=1)
    winner_basis: pl.Utf8 = field(
        "uncontested (Remarks), lot ('+1' vote mark on a tie) or top_vote (highest "
        "Obtained Valid Vote; the 2016 form has no winner flag).",
        isin=WINNER_BASIS,
    )
    tied: pl.Boolean = field(
        "Another candidate has the same top vote; true only for wins by lot, since a "
        "tie with no lot mark names no winner."
    )
    candidate_name: pl.Utf8 = nullable("Candidate Name.")
    gender: pl.Utf8 = nullable("Mapped gender.", isin=GENDERS)
    age: pl.Int32 = nullable("Reported age.", ge=0)
    category: pl.Utf8 = nullable("Category.")
    votes: pl.Int64 = nullable("Obtained Valid Vote; null when uncontested.", ge=0)
    margin: pl.Int64 = nullable("Votes ahead of the runner-up; null when uncontested.")

    class Config:
        strict = True
        unique: ClassVar[list[str]] = KEY


TABLES = {"seats": Seat, "candidates": Candidate, "winners": Winner}


class WinnerListRecord(pa.DataFrameModel):
    """One row of the SEC Mukhiya winner list (old-sec/wcl.aspx) for a block."""

    district_code: pl.Utf8 = keys()["district_code"]
    block_code: pl.Utf8 = field("Form block code.")
    unit_code: pl.Utf8 = field(
        "Frame panchayat code (unit_code in seats.parquet), found as match_basis "
        "states. Not the number at the end of seat_label, a territorial number "
        "that often differs (Bisfi/Bhairva/17 is unit 19)."
    )
    match_basis: pl.Utf8 = field(
        "seat_label: the ovc.aspx page for that seat printed the same label, "
        "ignoring case, spacing and zero padding; panchayat_name: the only "
        "unclaimed frame seat in the block with this panchayat name.",
        isin=["seat_label", "panchayat_name"],
    )
    sr_no: pl.Int32 = field(
        "SR No., the row's position in the block list across pages.", ge=1
    )
    panchayat_name: pl.Utf8 = field("Panchayat Name, verbatim.")
    seat_label: pl.Utf8 = field("Territorial seat (नि० क्षे० सं०), verbatim.")
    seat_reservation: pl.Utf8 = nullable("Reservation Status, verbatim.")
    winner_name: pl.Utf8 = field("Candidate Name, verbatim.")
    father_husband_name: pl.Utf8 = nullable("Father/Husband Name, verbatim.")
    gender_raw: pl.Utf8 = field("Gender, verbatim.")
    gender: pl.Utf8 = nullable("Gender mapped to male/female/other.", isin=GENDERS)
    age: pl.Int32 = nullable("Age; null when blank or above 120.", ge=0, le=120)
    age_raw: pl.Utf8 = nullable("Age, verbatim.")
    category: pl.Utf8 = nullable("Category, verbatim.")
    education: pl.Utf8 = nullable("Educational Qualification, verbatim.")
    mobile_number: pl.Utf8 = nullable("Mobile No., verbatim.")
    address: pl.Utf8 = nullable("Address, verbatim.")
    unit_repeated: pl.Boolean = field(
        "The list has another row for this seat. It repeats ovc.aspx's duplicated "
        "candidate entries (Suppi, Maniyari 02: RAMITA DEVI twice), so a seat can "
        "carry two rows; neither is dropped."
    )
    label_matches_frame: pl.Boolean = field(
        "Panchayat Name equals the seat frame's label for this unit_code, compared "
        "case-insensitively without spaces or punctuation."
    )
    source_file: pl.Utf8 = field("Winner-list ledger holding the saved page.")
    source_event: pl.Int32 = field(PROVENANCE["source_event"], ge=0)
    page: pl.Int16 = field("Winner-list grid page the row was on.", ge=1)
    source_row: pl.Int32 = field("Row on that grid page, from 1.", ge=1)
    fetched_at: pl.Utf8 = field(PROVENANCE["fetched_at"])
    page_sha256: pl.Utf8 = field(PROVENANCE["page_sha256"], str_length=64)

    class Config:
        strict = True
        unique: ClassVar[list[str]] = [
            "district_code",
            "block_code",
            "unit_code",
            "sr_no",
        ]

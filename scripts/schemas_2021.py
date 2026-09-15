"""Release contract for the 2021 panchayat tables: types, domains, keys, meanings.

Each model is the single source for a table's Arrow types, validation checks and
data dictionary; ``dictionary.csv`` and ``SCHEMA.json`` are generated from here.
"""

from typing import ClassVar

import pandera.polars as pa
import polars as pl

POSTS = {
    1: "Ward member (gram panchayat)",
    2: "Panch (gram kachahri)",
    3: "Mukhiya (gram panchayat head)",
    4: "Sarpanch (gram kachahri head)",
    5: "Panchayat samiti member",
    6: "Zila parishad member",
}
GENDERS = ["male", "female", "other"]
SEAT_STATUS = [
    "results",
    "one_candidate_no_results",
    "candidates_no_results",
    "no_candidates",
    "no_2021_phase",
]
MATCH_METHODS = [
    "serial_and_name",
    "name",
    "namesake_order",
    "name_contained",
    "serial_only",
]
WINNER_BASIS = ["result_flag", "sole_candidate"]


def field(description, **checks):
    return pa.Field(description=description, **checks)


def nullable(description, **checks):
    return pa.Field(description=description, nullable=True, **checks)


class Seat(pa.DataFrameModel):
    post_id: pl.Int8 = field("SEC post ID; see POSTS.", isin=list(POSTS))
    district_id: pl.Int32 = field("SEC district ID.", ge=1, le=38)
    block_id: pl.Int32 = nullable("SEC block ID; null for zila parishad seats.")
    panchayat_id: pl.Int64 = nullable(
        "SEC panchayat ID; null for samiti and zila parishad seats."
    )
    seat_no: pl.Int32 = nullable(
        "Ward, samiti or zila parishad seat number; null for mukhiya and sarpanch."
    )
    unit_id: pl.Utf8 = field("Seat key within the office, built from the IDs.")
    district: pl.Utf8 = field("District name from the portal frame.")
    block: pl.Utf8 = nullable("Block name from the portal frame.")
    panchayat: pl.Utf8 = nullable("Panchayat name from the portal frame.")
    phases_listed: pl.Utf8 = nullable(
        "Election rounds the portal lists for the seat, ';'-joined (e.g. "
        "2021_1;2023_1); null when not requested."
    )
    candidate_records: pl.Int32 = field("Rows in the 2021 candidate list.", ge=0)
    result_records: pl.Int32 = field(
        "Rows in the 2021 result feed; samiti and zila parishad seats have one "
        "row per candidate per panchayat.",
        ge=0,
    )
    result_only_candidates: pl.Int32 = field(
        "Candidates named in results but missing from the candidate list.", ge=0
    )
    result_candidates: pl.Int32 = field("Distinct candidates in the results.", ge=0)
    winners_flagged: pl.Int32 = field(
        "Candidates with IsWin true on any result row.", ge=0, le=1
    )
    winner_flag_partial: pl.Boolean = field(
        "IsWin differs across the winner's panchayat rows in the source."
    )
    status: pl.Utf8 = field("Seat outcome class; see SEAT_STATUS.", isin=SEAT_STATUS)

    class Config:
        strict = True
        unique: ClassVar[list[str]] = ["post_id", "unit_id"]


PROVENANCE = {
    "source_url": "SEC request URL, including election phase and seat parameters.",
    "fetched_at": "UTC time the response was retrieved.",
    "source_sha256": "SHA-256 of the saved response body.",
    "source_row": "One-based position of the record in that response.",
}


class Candidate(pa.DataFrameModel):
    post_id: pl.Int8 = field("SEC post ID.", isin=list(POSTS))
    unit_id: pl.Utf8 = field("Seat key; joins to seats.")
    in_candidate_list: pl.Boolean = field(
        "Listed in the candidate list; false for candidates named only in results, "
        "whose list attributes are null."
    )
    candidate_serial: pl.Int32 = nullable(
        "OrderBy in the candidate list (renumbered in name order); null if unlisted.",
        ge=1,
    )
    candidate_name: pl.Utf8 = nullable(
        "CandidateName, verbatim; the result-feed name without the winner mark "
        "when unlisted; null when blank in the source (one panch candidate)."
    )
    guardian_name: pl.Utf8 = nullable("GaurdianName (father or husband), verbatim.")
    candidate_age: pl.Int32 = nullable("Age as reported; not corrected.", ge=0)
    candidate_age_implausible: pl.Boolean = nullable("Age below 21 or above 100.")
    candidate_gender_raw: pl.Utf8 = nullable("Gender, verbatim.")
    candidate_gender: pl.Utf8 = nullable(
        "Gender mapped to male/female/other.", isin=GENDERS
    )
    candidate_address: pl.Utf8 = nullable("CandidateAddress, verbatim.")
    symbol_name: pl.Utf8 = nullable("SymbolName, the allotted election symbol.")
    symbol_file: pl.Utf8 = nullable("SymbolUrl, the symbol image file name.")
    photo_url: pl.Utf8 = nullable("CandidatePhoto link.", str_startswith="http")
    affidavit_url: pl.Utf8 = nullable(
        "CandidateDoc nomination PDF link.", str_startswith="http"
    )
    result_present: pl.Boolean = field("A result record was matched to this candidate.")
    result_serial: pl.Int32 = nullable("OrderBy of the matched result record.")
    match_method: pl.Utf8 = nullable(
        "How the result was matched; null without a result.", isin=MATCH_METHODS
    )
    votes: pl.Int64 = nullable(
        "TotalVote summed over the seat's result rows; null without results.", ge=0
    )
    elected: pl.Boolean = nullable("IsWin from the result feed; null without results.")
    source_url: pl.Utf8 = field(PROVENANCE["source_url"])
    fetched_at: pl.Utf8 = field(PROVENANCE["fetched_at"])
    source_sha256: pl.Utf8 = field(PROVENANCE["source_sha256"], str_length=64)
    source_row: pl.Int32 = field(PROVENANCE["source_row"], ge=1)

    class Config:
        strict = True
        unique: ClassVar[list[str]] = ["source_url", "source_row"]


class ResultRow(pa.DataFrameModel):
    post_id: pl.Int8 = field("SEC post ID.", isin=list(POSTS))
    unit_id: pl.Utf8 = field("Seat key; joins to seats.")
    result_record_id: pl.Int64 = field("SlNo, the portal's result record number.")
    post_name: pl.Utf8 = field("PostName, verbatim.")
    result_district_id: pl.Int32 = field("Dist; equals the requested district.")
    result_district: pl.Utf8 = field("DistrictName, verbatim.")
    result_block_id: pl.Int32 = nullable("BlockID of the reporting panchayat.")
    result_block: pl.Utf8 = nullable("BlockName, verbatim.")
    result_panchayat_id: pl.Int64 = nullable("PanchayatNo of the reporting panchayat.")
    result_panchayat: pl.Utf8 = nullable("PanchayatName, verbatim.")
    result_seat_no: pl.Int32 = nullable("WardNo: ward, samiti or zila parishad number.")
    result_serial: pl.Int32 = nullable(
        "OrderBy in the result feed; null in 16,113 ward-member rows.", ge=1
    )
    result_name: pl.Utf8 = field("CandidateName in the result feed, verbatim.")
    votes: pl.Int64 = nullable("TotalVote in this panchayat; null when blank.", ge=0)
    elected: pl.Boolean = field("IsWin.")
    candidate_serial: pl.Int32 = nullable(
        "Matched candidate-list serial; null when the candidate is not listed."
    )
    match_method: pl.Utf8 = nullable(
        "How the match was made; null when unlisted.", isin=MATCH_METHODS
    )
    source_url: pl.Utf8 = field(PROVENANCE["source_url"])
    fetched_at: pl.Utf8 = field(PROVENANCE["fetched_at"])
    source_sha256: pl.Utf8 = field(PROVENANCE["source_sha256"], str_length=64)
    source_row: pl.Int32 = field(PROVENANCE["source_row"], ge=1)

    class Config:
        strict = True
        unique: ClassVar[list[str]] = ["post_id", "unit_id", "source_row"]


class Winner(pa.DataFrameModel):
    post_id: pl.Int8 = field("SEC post ID.", isin=list(POSTS))
    unit_id: pl.Utf8 = field("Seat key; joins to seats.")
    winner_basis: pl.Utf8 = field(
        "result_flag (IsWin) or sole_candidate (one candidate, no results; "
        "inferred as elected unopposed).",
        isin=WINNER_BASIS,
    )
    candidate_serial: pl.Int32 = nullable("Candidate-list serial; null if unlisted.")
    result_serial: pl.Int32 = nullable("Result serial; null for sole candidates.")
    winner_name: pl.Utf8 = field("Candidate-list name, else the result name.")
    candidate_gender: pl.Utf8 = nullable(
        "Mapped gender; null if unlisted.", isin=GENDERS
    )
    candidate_age: pl.Int32 = nullable("Reported age; null if unlisted.", ge=0)
    votes: pl.Int64 = nullable("Votes summed over result rows.", ge=0)
    affidavit_url: pl.Utf8 = nullable(
        "Nomination PDF link; null if unlisted.", str_startswith="http"
    )

    class Config:
        strict = True
        unique: ClassVar[list[str]] = ["post_id", "unit_id"]


class CurrentWinner(pa.DataFrameModel):
    post_id: pl.Int8 = field("SEC post ID.", isin=list(POSTS))
    unit_id: pl.Utf8 = nullable(
        "Matched seat key; null if the seat is not in the frame."
    )
    district_id: pl.Int32 = field("Dist.")
    block_id: pl.Int32 = field("BlockID.")
    panchayat_id: pl.Int64 = nullable("PanchayatNo; null for zila parishad.")
    seat_no: pl.Int32 = nullable("WardNo; null for mukhiya and sarpanch.")
    district: pl.Utf8 = field("District, verbatim.")
    block: pl.Utf8 = field("Block, verbatim.")
    panchayat: pl.Utf8 = nullable("Panchayat, verbatim.")
    post_name: pl.Utf8 = field("Post, verbatim.")
    vacant_placeholder: pl.Boolean = field(
        "Portal placeholder for a vacant seat: no name, age 55, a date in the photo "
        "field; person fields are null."
    )
    placeholder_date: pl.Utf8 = nullable("Date shown in a placeholder's photo field.")
    placeholder_affidavit: pl.Utf8 = nullable("Affidavit field text of a placeholder.")
    candidate_name: pl.Utf8 = nullable("CandidateName, verbatim; null if vacant.")
    guardian_name: pl.Utf8 = nullable("GuardianName, verbatim.")
    candidate_gender_raw: pl.Utf8 = nullable("Gender, verbatim.")
    candidate_age: pl.Int32 = nullable("Age as reported.", ge=0)
    candidate_address: pl.Utf8 = nullable("Address, verbatim.")
    candidate_category: pl.Utf8 = nullable("Category: candidate's caste category.")
    reservation_for_reported: pl.Utf8 = nullable("ReservationFor: women or other.")
    reservation_status_reported: pl.Utf8 = nullable("ReservationStatus, verbatim.")
    photo_url: pl.Utf8 = nullable("CandidatePhotos link.", str_startswith="http")
    affidavit_url: pl.Utf8 = nullable("Affidavit link.", str_startswith="http")
    source_url: pl.Utf8 = field(PROVENANCE["source_url"])
    fetched_at: pl.Utf8 = field(PROVENANCE["fetched_at"])
    source_sha256: pl.Utf8 = field(PROVENANCE["source_sha256"], str_length=64)
    source_row: pl.Int32 = field(PROVENANCE["source_row"], ge=1)

    class Config:
        strict = True
        unique: ClassVar[list[str]] = ["source_url", "source_row"]


class CurrentReservation(pa.DataFrameModel):
    post_id: pl.Int8 = field("SEC post ID.", isin=list(POSTS))
    unit_id: pl.Utf8 = nullable(
        "Matched seat key; null if the seat is not in the frame."
    )
    district_id: pl.Int32 = field("Dist.")
    block_id: pl.Int32 = field("BlockID.")
    panchayat_id: pl.Int64 = nullable("PanchayatNo; null for zila parishad.")
    seat_no: pl.Int32 = nullable("WardNo; null for mukhiya and sarpanch.")
    district: pl.Utf8 = field("District, verbatim.")
    block: pl.Utf8 = field("Block, verbatim.")
    panchayat: pl.Utf8 = nullable("Panchayat, verbatim.")
    post_name: pl.Utf8 = field("Post, verbatim.")
    seat_reservation: pl.Utf8 = field("Reservation: category (women/other), verbatim.")
    source_url: pl.Utf8 = field(PROVENANCE["source_url"])
    fetched_at: pl.Utf8 = field(PROVENANCE["fetched_at"])
    source_sha256: pl.Utf8 = field(PROVENANCE["source_sha256"], str_length=64)
    source_row: pl.Int32 = field(PROVENANCE["source_row"], ge=1)

    class Config:
        strict = True
        unique: ClassVar[list[str]] = ["source_url", "source_row"]


TABLES = {
    "seats": Seat,
    "candidates": Candidate,
    "result_rows": ResultRow,
    "winners": Winner,
    "current_winners": CurrentWinner,
    "current_reservations": CurrentReservation,
}


def polars_schema(model):
    return {
        name: column.dtype.type for name, column in model.to_schema().columns.items()
    }


def dictionary_rows(name, model):
    schema = model.to_schema()
    for column, spec in schema.columns.items():
        yield {
            "table": f"{name}.parquet",
            "column": column,
            "type": str(spec.dtype),
            "nullable": spec.nullable,
            "checks": "; ".join(str(c) for c in spec.checks),
            "description": spec.description,
        }

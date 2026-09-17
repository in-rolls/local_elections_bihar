"""The audit's comparisons must fail on a planted defect; no live requests."""

import audit_2016 as a
import build_2016 as b
import polars as pl
from test_build_2016 import candidate, page, write_inputs


def release(tmp_path):
    first = [candidate(str(n), f"C{n}", str(100 - n)) for n in range(1, 21)]
    views = [
        ("01", 1, page(first, number=1, pages=2)),
        ("01", 2, page([candidate("21", "C21", "500")], number=2, pages=2)),
        ("02", 1, page([candidate("01", "U", "--", "Uncontested")])),
    ]
    frame, results = write_inputs(tmp_path, views)
    b.build(frame, results, tmp_path / "out")
    tables = [pl.read_parquet(tmp_path / f"out/{n}.parquet") for n in a_tables()]
    return frame, *tables


def a_tables():
    return ("seats", "candidates", "winners")


def legacy(tmp_path, seats, candidates, change=None):
    """Legacy-shaped files: mukhiya rows keyed by panchayat label, the rest empty."""
    rows = a.release_rows(seats, candidates).drop(
        "panchayat", "code_repeated", "office"
    )
    rows = rows.rename({"unit": "panchayat"}).with_columns(pl.lit(" ").alias("email"))
    if change is not None:
        rows = change(rows)
    folder = tmp_path / "fin"
    folder.mkdir()
    for office, unit in a.LEGACY_UNIT.items():
        table = rows if office == "mukhiya" else rows.clear()
        if unit != "panchayat":
            table = table.with_columns(pl.col("panchayat").alias(unit))
        table.write_parquet(folder / f"{office}.parquet")
    return folder


def test_identical_legacy_rows_raise_no_flag(tmp_path):
    _, seats, candidates, _ = release(tmp_path)
    report, flags = a.compare_legacy(
        seats, candidates, legacy(tmp_path, seats, candidates)
    )
    assert flags == []
    assert report["offices"]["mukhiya"]["identical_rows"] == 22


def test_a_dropped_second_page_is_reported(tmp_path):
    _, seats, candidates, _ = release(tmp_path)
    folder = legacy(tmp_path, seats, candidates)
    report, flags = a.compare_legacy(
        seats, candidates.filter(pl.col("page") == 1), folder
    )
    assert flags == ["legacy_differs_mukhiya"]
    assert report["offices"]["mukhiya"]["legacy_only_rows"] == 1


def test_a_changed_vote_and_a_changed_reservation_are_reported(tmp_path):
    _, seats, candidates, _ = release(tmp_path)

    def change(rows):
        return rows.with_columns(
            pl.when(pl.col("candidate_name") == "C3")
            .then(pl.lit("9"))
            .otherwise(pl.col("valid_vote"))
            .alias("valid_vote"),
            pl.when(pl.col("panchayat") == "02 - P")
            .then(pl.lit("अनारक्षित(महिला)"))
            .otherwise(pl.col("reservation_status"))
            .alias("reservation_status"),
        )

    folder = legacy(tmp_path, seats, candidates, change)
    report, flags = a.compare_legacy(seats, candidates, folder)
    assert flags == ["legacy_differs_mukhiya", "legacy_reservation_differs_mukhiya"]
    office = report["offices"]["mukhiya"]
    assert (office["legacy_only_rows"], office["release_only_rows"]) == (1, 1)
    assert office["seats_reservation_differs"] == 1


def test_frame_and_consistency_checks(tmp_path):
    frame, seats, candidates, winners = release(tmp_path)
    frame = pl.read_parquet(frame)
    assert a.compare_frame(seats, frame)[1] == []
    assert a.compare_frame(seats.head(1), frame)[1] == ["frame_office_counts"]
    women = seats.with_columns(pl.lit("अनारक्षित(महिला)").alias("seat_reservation"))
    men = candidates.with_columns(
        pl.when(pl.col("sr_no") == 4)
        .then(pl.lit("male"))
        .otherwise(pl.col("gender"))
        .alias("gender")
    )
    report, _ = a.consistency(women, men, winners)
    assert report["non_female_candidates_in_women_seats"] == 1
    shifted = candidates.with_columns(pl.lit(1, pl.Int16).alias("page"))
    assert a.consistency(seats, shifted, winners)[1] == ["rows_not_matching_page_count"]

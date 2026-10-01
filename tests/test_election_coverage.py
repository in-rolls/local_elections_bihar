"""Coverage counts must not turn ambiguous joins or snapshots into verified history."""

from pathlib import Path

import polars as pl
import pytest

from scripts.reporting.summary import event_rows, report


def inputs():
    seats = pl.DataFrame(
        {
            "post_id": [3, 3, 3, 3],
            "unit_id": ["a", "b", "b", "c"],
            "seat_reservation": ["SC (women)", None, None, ""],
        }
    )
    candidates = pl.DataFrame(
        {
            "post_id": [3, 3, 3],
            "unit_id": ["a", "a", "b"],
            "votes": [0, 12, None],
        }
    )
    winners = pl.DataFrame(
        {
            "post_id": [3, 3],
            "unit_id": ["a", "b"],
            "winner_basis": ["result_flag", "sole_candidate"],
        }
    )
    return seats, candidates, winners


def summarize(seats, candidates, winners, snapshot=None):
    rows = event_rows(
        seats,
        candidates,
        winners,
        ["post_id", "unit_id"],
        "post_id",
        "2021_general",
        2021,
        snapshot,
    )
    return next(r for r in rows if r["office"] == "mukhiya")


def test_ambiguous_seat_codes_do_not_multiply_coverage():
    row = summarize(*inputs())
    assert row["seat_frame_rows"] == 4
    assert row["ambiguous_seat_rows"] == 2
    assert row["seats_with_candidates"] == 1
    assert row["seats_with_winners"] == 1
    assert row["candidate_records"] == 3
    assert row["candidate_records_with_votes"] == 2
    assert row["winner_records"] == 2
    assert row["winners_source_flagged"] == 1
    assert row["winners_derived"] == 1
    assert row["seats_with_election_reservation_label"] == 1


def test_snapshot_does_not_supply_election_reservation():
    seats, candidates, winners = inputs()
    snapshot = pl.DataFrame(
        {
            "post_id": [3, 3, 3],
            "unit_id": ["a", "b", "c"],
            "seat_reservation": ["SC (women)", "unreserved", "   "],
        }
    )
    row = summarize(seats.drop("seat_reservation"), candidates, winners, snapshot)
    assert row["seats_with_election_reservation_label"] is None
    assert row["seats_with_snapshot_reservation_label"] == 1
    assert row["cross_general_election_link_status"] == "not_established"


def test_null_geographic_components_can_join():
    seats, candidates, winners = inputs()
    seats, candidates, winners = [
        df.with_columns(pl.lit(None, dtype=pl.String).alias("parent"))
        for df in (seats, candidates, winners)
    ]
    rows = event_rows(
        seats,
        candidates,
        winners,
        ["post_id", "unit_id", "parent"],
        "post_id",
        "event",
        2016,
    )
    assert next(r for r in rows if r["office"] == "mukhiya")["seats_with_winners"] == 1


def test_orphan_candidates_fail_instead_of_disappearing():
    seats, candidates, winners = inputs()
    candidates = candidates.with_columns(pl.lit("unknown").alias("unit_id"))
    with pytest.raises(ValueError, match="candidates refer to seats outside"):
        summarize(seats, candidates, winners)


def test_multiple_winners_are_not_silently_counted_as_one():
    seats, candidates, winners = inputs()
    with pytest.raises(ValueError, match="multiple winner records"):
        summarize(seats, candidates, pl.concat([winners, winners.head(1)]))


def test_repeated_snapshot_seats_fail():
    snapshot = inputs()[0]
    snapshot = snapshot.with_columns(pl.lit("unreserved").alias("seat_reservation"))
    with pytest.raises(ValueError, match="Snapshot has repeated seat keys"):
        summarize(*inputs(), snapshot)


def test_report_preserves_elections_and_provisional_source_limits():
    table, metadata = report(Path("data"))
    assert table.height == 34
    general = table.filter(pl.col("event") == "2021_general")
    assert general["seat_frame_rows"].sum() == 247671
    assert general["winner_records"].sum() == 244475
    assert general["seats_with_election_reservation_label"].null_count() == 6
    by = table.filter(pl.col("event").str.ends_with("_byelection"))
    assert by["event"].n_unique() == 3
    assert by["seat_frame_rows"].sum() == 5749
    claims = table.filter(
        pl.col("coverage_basis").is_in(["winner_list", "runner_up_list"])
    )
    assert claims["seat_frame_rows"].null_count() == 3
    assert claims["candidate_records"].null_count() == 3
    dated = claims.filter(pl.col("election_year") == 2011)
    assert dated["winner_claim_records"].drop_nulls().to_list() == [330, 3973]
    assert claims["election_year"].null_count() == 0
    district = claims.filter(pl.col("collection") == "mukhiya_reports_winner_records")
    assert district["winner_claim_records"].to_list() == [3973]
    court = table.filter(pl.col("collection") == "khajuria_judgment")
    assert court["candidate_records"].to_list() == [11]
    assert court["winner_records"].to_list() == [1]
    assert all(len(v["sha256"]) == 64 for v in metadata["inputs"].values())


def test_unknown_office_is_not_silently_omitted():
    changed = [df.with_columns(pl.lit(9).alias("post_id")) for df in inputs()]
    with pytest.raises(ValueError, match="unrecognized office"):
        summarize(*changed)


def test_summary_preserves_counts_and_counts_storage_once(tmp_path):
    from scripts.reporting.summary import summary_markdown, update_readme

    data = Path("data")
    import json

    provenance = json.loads((data / "PROVENANCE.json").read_text())
    text = summary_markdown(provenance)
    assert "scripts.year2011.parse_reports" in text
    assert "scripts.sources" in text
    assert "2011/gaya_mukhiya/runner_up_records.parquet" in text
    assert "SHA-256 in PROVENANCE.json" in text
    path = tmp_path / "README.md"
    path.write_text(
        "Before\n<!-- data-summary:start -->\nold\n<!-- data-summary:end -->\nAfter\n"
    )
    update_readme(path, text)
    assert path.read_text().startswith("Before\n")
    assert path.read_text().endswith("\nAfter\n")
    assert path.read_text().count("| Collection |") == 1
    before = path.read_text()
    update_readme(path, text)
    assert path.read_text() == before

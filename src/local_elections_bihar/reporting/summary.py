"""Generate the data guide from published records and provenance."""

import argparse
import hashlib
import json
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from local_elections_bihar.year2016.schema import KEY as KEY_2016

OFFICES = {
    1: "ward_member",
    2: "panch",
    3: "mukhiya",
    4: "sarpanch",
    5: "panchayat_samiti_member",
    6: "zila_parishad_member",
}
DESCRIPTIONS = {
    "collection": "Parsed source collection; provisional sources stay separate.",
    "election_year": "Established election year; null for undated source claims.",
    "event": "General election, by-election round, or provisional source collection.",
    "office": "One of the six panchayat offices.",
    "coverage_basis": (
        "Seat frame, winner/runner list, or a single-contest judgment transcription."
    ),
    "seat_frame_rows": (
        "Known frame rows, including ambiguous source codes; null without a frame."
    ),
    "ambiguous_seat_rows": (
        "Frame rows whose source key identifies more than one seat label."
    ),
    "seats_with_candidates": (
        "Unambiguous frame seats with at least one candidate record."
    ),
    "seats_with_winners": (
        "Unambiguous frame seats with a winner in the parsed winner table."
    ),
    "seats_with_election_reservation_label": (
        "Frame rows with a nonblank election-specific source label; not "
        "independent verification."
    ),
    "seats_with_snapshot_reservation_label": (
        "Unambiguous frame seats with a label in the undated term snapshot; not "
        "historical assignment verification."
    ),
    "candidate_records": (
        "Published candidate rows; null when only winner/runner records are parsed."
    ),
    "candidate_records_with_votes": (
        "Candidate rows with a nonnull vote count; observed zero counts as present."
    ),
    "winner_records": (
        "Published winner records, which may have ambiguous seat identities."
    ),
    "winners_source_flagged": "Winner records explicitly flagged in result feeds.",
    "winners_derived": (
        "Winner records derived from votes, lots, uncontested status or sole candidacy."
    ),
    "winner_claim_records": (
        "Rows asserted to be winners in provisional source lists; not reconciled seats."
    ),
    "runner_up_records": (
        "Rows from a provisional runner-up list, not a complete candidate roster."
    ),
    "records_with_reservation_label": (
        "Provisional source records with nonblank reservation text; not a "
        "unique-seat count."
    ),
    "cross_general_election_link_status": (
        "Whether links between general-election seat frames have been established."
    ),
}


def present(table, column):
    if column not in table.columns:
        return None
    return table.filter(
        pl.col(column).is_not_null()
        & (pl.col(column).cast(pl.String).str.strip_chars() != "")
    )


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def event_rows(
    seats, candidates, winners, keys, office_column, event, year, snapshot=None
):
    """Count joins while keeping ambiguous codes and snapshot dates explicit."""
    allowed = set(OFFICES) if office_column == "post_id" else set(OFFICES.values())
    for table in (seats, candidates, winners):
        if set(table[office_column].unique()) - allowed:
            raise ValueError(f"{event}: unrecognized office")
    seat_keys = seats.select(keys).unique()
    for name, table in [("candidates", candidates), ("winners", winners)]:
        if table.join(seat_keys, on=keys, how="anti", nulls_equal=True).height:
            raise ValueError(f"{event}: {name} refer to seats outside the frame")
    if winners.select(keys).is_duplicated().any():
        raise ValueError(f"{event}: multiple winner records for one source seat key")
    if snapshot is not None:
        snapshot = present(snapshot, "seat_reservation")
        if snapshot.select(keys).is_duplicated().any():
            raise ValueError("Snapshot has repeated seat keys")
    bases = set(winners["winner_basis"].unique())
    if bases - {"result_flag", "sole_candidate", "uncontested", "lot", "top_vote"}:
        raise ValueError(f"Unrecognized winner basis: {bases}")
    rows = []
    for post, office in OFFICES.items():
        value = post if office_column == "post_id" else office
        ss = seats.filter(pl.col(office_column) == value)
        cc = candidates.filter(pl.col(office_column) == value)
        ww = winners.filter(pl.col(office_column) == value)
        ambiguous = ss.group_by(keys).len().filter(pl.col("len") > 1).select(keys)
        unique = ss.join(ambiguous, on=keys, how="anti", nulls_equal=True)
        reserved = present(ss, "seat_reservation")
        rows.append(
            {
                "collection": str(year) if year == 2016 else "2021_term",
                "election_year": year,
                "event": event,
                "office": office,
                "coverage_basis": "seat_frame",
                "seat_frame_rows": ss.height,
                "ambiguous_seat_rows": ss.height - unique.height,
                "seats_with_candidates": unique.join(
                    cc.select(keys).unique(), on=keys, how="semi", nulls_equal=True
                ).height,
                "seats_with_winners": unique.join(
                    ww.select(keys), on=keys, how="semi", nulls_equal=True
                ).height,
                "seats_with_election_reservation_label": (
                    None if reserved is None else reserved.height
                ),
                "seats_with_snapshot_reservation_label": (
                    None
                    if snapshot is None
                    else unique.join(snapshot, on=keys, how="semi").height
                ),
                "candidate_records": cc.height,
                "candidate_records_with_votes": cc["votes"].is_not_null().sum(),
                "winner_records": ww.height,
                "winners_source_flagged": ww.filter(
                    pl.col("winner_basis") == "result_flag"
                ).height,
                "winners_derived": ww.filter(
                    pl.col("winner_basis") != "result_flag"
                ).height,
                "winner_claim_records": None,
                "runner_up_records": None,
                "records_with_reservation_label": None,
                "cross_general_election_link_status": "not_established",
            }
        )
    return rows


def report(data):
    inputs, rows = {}, []

    def read(relative):
        path = data / relative
        inputs[relative] = {"sha256": sha256(path), "bytes": path.stat().st_size}
        return pl.read_parquet(path)

    rows.extend(
        event_rows(
            *(
                read(f"2016/{name}.parquet")
                for name in ["seats", "candidates", "winners"]
            ),
            KEY_2016,
            "office",
            "2016_general",
            2016,
        )
    )
    snapshot = read("2021/current_reservations.parquet")
    rows.extend(
        event_rows(
            *(
                read(f"2021/{name}.parquet")
                for name in ["seats", "candidates", "winners"]
            ),
            ["post_id", "unit_id"],
            "post_id",
            "2021_general",
            2021,
            snapshot,
        )
    )
    bye = [
        read(f"2021/byelection_{name}.parquet")
        for name in ["seats", "candidates", "winners"]
    ]
    phases = set(bye[0]["phase"].unique())
    if any(set(df["phase"].unique()) - phases for df in bye[1:]):
        raise ValueError("By-election records refer to a round outside the frame")
    for phase in sorted(phases):
        rows.extend(
            event_rows(
                *(df.filter(pl.col("phase") == phase) for df in bye),
                ["post_id", "unit_id"],
                "post_id",
                phase + "_byelection",
                int(phase[:4]),
                snapshot,
            )
        )
    for name, year, outcome in [
        ("gaya_mukhiya/spreadsheet_winner_records", 2011, "winner"),
        ("mukhiya_reports/winner_records", 2011, "winner"),
        ("gaya_mukhiya/runner_up_records", 2011, "runner"),
    ]:
        df = read(f"2011/{name}.parquet")
        if df["election_year"].unique().to_list() != [year]:
            raise ValueError(f"Update coverage classification for changed {name} year")
        reserved = present(df, "reservation_raw")
        row = dict.fromkeys(DESCRIPTIONS)
        row.update(
            collection=name.replace("/", "_"),
            election_year=year,
            event="2011_general_source_claim" if year else "undated_source_claim",
            office="mukhiya",
            coverage_basis="winner_list" if outcome == "winner" else "runner_up_list",
            winner_claim_records=df.height if outcome == "winner" else None,
            runner_up_records=df.height if outcome == "runner" else None,
            records_with_reservation_label=None
            if reserved is None
            else reserved.height,
            cross_general_election_link_status="not_established",
        )
        rows.append(row)
    path = "2011/khajuria_judgment/candidates.csv"
    court = pl.read_csv(data / path)
    inputs[path] = {
        "sha256": sha256(data / path),
        "bytes": (data / path).stat().st_size,
    }
    row = dict.fromkeys(DESCRIPTIONS)
    row.update(
        collection="khajuria_judgment",
        election_year=2011,
        event="2011_general_judgment_transcription",
        office="mukhiya",
        coverage_basis="single_contest_judgment",
        candidate_records=court.height,
        candidate_records_with_votes=court["votes"].is_not_null().sum(),
        winner_records=court.filter(pl.col("initial_outcome") == "elected").height,
        cross_general_election_link_status="not_established",
    )
    rows.append(row)
    schema = {
        key: pl.String
        if key
        in {
            "collection",
            "event",
            "office",
            "coverage_basis",
            "cross_general_election_link_status",
        }
        else pl.Int64
        for key in DESCRIPTIONS
    }
    table = pl.DataFrame(rows, schema=schema)
    metadata = {
        "columns": DESCRIPTIONS,
        "types": {name: str(dtype) for name, dtype in table.schema.items()},
        "missing": "Blank CSV numeric cells are unknown/unavailable, not zero.",
        "limits": [
            (
                "District Mukhiya reports include the 338 Gaya pilot PDF records, "
                "counted once here. The Khajuria judgment winner overlaps one "
                "district-report record; source totals are not additive."
            ),
            (
                "A reported reservation label is not independent confirmation of its "
                "correctness."
            ),
            (
                "Current-term reservations are not assigned to general or by-elections "
                "retrospectively."
            ),
            (
                "Seat coverage is conditional on the collected frame, not proof of "
                "statewide completeness."
            ),
            (
                "2011 winner/runner records do not establish a unique-seat frame or "
                "all-candidate coverage."
            ),
            (
                "Cross-general-election links have not been established; within-term "
                "by-election membership already exists separately."
            ),
        ],
        "unparsed_sources": [
            "unprocessed/2006/workbooks",
            "unprocessed/undated/workbooks",
        ],
        "partially_parsed_sources": ["2011/raw/reports"],
        "inputs": inputs,
        "producer_sha256": sha256(Path(__file__)),
    }
    return table, metadata


START = "<!-- data-summary:start -->"
END = "<!-- data-summary:end -->"


def size_label(size):
    for unit, divisor in [("GB", 10**9), ("MB", 10**6), ("KB", 10**3)]:
        if size >= divisor:
            return f"{size / divisor:,.2f} {unit}"
    return f"{size:,} B"


def summary_markdown(provenance):
    """Render sources and the ordered script chain without mounting raw storage."""
    lines = [
        "| Collection | Required originals | Processing chain | "
        "Published outputs | Archive |",
        "| --- | --- | --- | --- | --- |",
    ]
    for year, pipeline in provenance["pipelines"].items():
        sources = "<br>".join(
            provenance["source_groups"][name]["purpose"] for name in pipeline["inputs"]
        )
        chain = " → ".join(f"`{step['module']}`" for step in pipeline["steps"])
        outputs = "<br>".join(f"`{path}`" for path in pipeline["outputs"])
        archives = provenance["archives"].get(year, [])
        status = "Publication pending"
        if archives:
            count = sum(archive["source_files"] for archive in archives)
            size = sum(archive["source_bytes"] for archive in archives)
            links = "<br>".join(
                f"[{archive['filename']}]({archive['url']})"
                if archive.get("url")
                else "Publication pending"
                for archive in archives
            )
            status = f"{count:,} originals; {size_label(size)}; {links}"
        lines.append(f"| {year} | {sources} | {chain} | {outputs} | {status} |")
    lines.extend(
        [
            "",
            "Run `make parse YEAR=<year>` for the complete ordered chain. "
            "Intermediate geography tables are disposable `.cache/` files.",
            "",
        ]
    )
    lines.extend(
        f"- {limit}"
        for limit in provenance["interpretation"].values()
        if isinstance(limit, str)
    )
    return "\n".join(lines)


def published_files(data):
    units = {
        "seats": "Seat in the election frame",
        "candidates": "Candidate record",
        "winners": "Winner record, with determination basis",
        "result_rows": "Source result record; see dataset grain",
        "current_winners": "Undated current-term winner-feed record",
        "current_reservations": "Undated current-term seat-reservation record",
        "byelection_seats": "Seat in a by-election round",
        "byelection_candidates": "Candidate in a by-election round",
        "byelection_result_rows": "Source result record in a by-election round",
        "byelection_winners": "Winner in a by-election round",
        "winner_records": (
            "Mukhiya winner reported in a 2011 district PDF "
            "(23 districts, including Gaya)"
        ),
        "spreadsheet_winner_records": "Gaya Mukhiya winner with GP and block (Excel)",
        "runner_up_records": (
            "Gaya Mukhiya runner-up with GP linked from the companion winner PDF"
        ),
    }
    paths = sorted(
        [
            *data.glob("2016/*.parquet"),
            *data.glob("2021/*.parquet"),
            data / "2011/mukhiya_reports/winner_records.parquet",
            data / "2011/gaya_mukhiya/spreadsheet_winner_records.parquet",
            data / "2011/gaya_mukhiya/runner_up_records.parquet",
        ]
    )
    lines = ["| File | Rows | Each row represents |", "| --- | ---: | --- |"]
    for path in paths:
        relative = path.relative_to(data).as_posix()
        rows = pq.read_metadata(path).num_rows
        lines.append(
            f"| [{relative}](data/{relative}) | {rows:,} | {units[path.stem]} |"
        )
    return "\n".join(lines)


def update_readme(path, markdown, start=START, end=END):
    text = path.read_text()
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("README must contain exactly one data-summary marker pair")
    before, rest = text.split(start)
    _, after = rest.split(end)
    path.write_text(before + start + "\n\n" + markdown + "\n\n" + end + after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    args = parser.parse_args()
    provenance = json.loads((args.data / "PROVENANCE.json").read_text())
    path = args.data / "README.md"
    update_readme(path, summary_markdown(provenance))
    update_readme(
        args.data.parent / "README.md",
        published_files(args.data),
        "<!-- datasets:start -->",
        "<!-- datasets:end -->",
    )
    print(f"Updated one generated summary table in {path}")


if __name__ == "__main__":
    main()

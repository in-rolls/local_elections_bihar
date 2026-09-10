"""Guard source-row retention, duplicate linkage, and streaming output safety."""

import csv

import pyarrow.parquet as pq
import pytest
import to_parquet as convert


def save(path, contract, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(contract["columns"])
        writer.writerows(rows)
    return path


def row_for(contract, name="उदाहरण"):
    fields = dict.fromkeys(contract["columns"], "")
    fields.update(
        post=contract["post"],
        candidate_name=name,
        valid_vote="0010",
        number="001",
        reservation_status="Source seat category",
        category="Source candidate category",
    )
    return list(fields.values())


@pytest.mark.parametrize("name", convert.CONTRACTS)
def test_each_office_preserves_distinct_categories_and_strings(tmp_path, name):
    contract = convert.CONTRACTS[name]
    source = save(tmp_path / name, contract, [row_for(contract)])
    target = tmp_path / "release.parquet"
    counts = convert.convert(source, target, contract)
    assert counts == {"rows": 1, "duplicate_rows": 0, "missing_candidates": 0}
    assert convert.convert(source, target, contract, check=True) == counts
    row = pq.read_table(target).to_pylist()[0]
    assert row["valid_vote"] == "0010"
    assert row["number"] == "001"
    assert row["reservation_status"] == "Source seat category"
    assert row["category"] == "Source candidate category"
    assert row["year"] == 2016
    assert row["duplicate_of_source_row"] is None


def test_duplicate_links_cross_batch_boundaries_without_dropping_rows(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(convert, "BATCH_SIZE", 2)
    contract = next(iter(convert.CONTRACTS.values()))
    row = row_for(contract)
    source = save(
        tmp_path / "source.csv", contract, [row, row_for(contract, "Other"), row]
    )
    target = tmp_path / "release.parquet"
    counts = convert.convert(source, target, contract)
    assert counts["rows"] == 3
    assert counts["duplicate_rows"] == 1
    assert pq.read_table(target)["duplicate_of_source_row"].to_pylist() == [
        None,
        None,
        1,
    ]
    convert.convert(source, target, contract, check=True)


def test_missing_candidate_is_retained_and_flagged(tmp_path):
    contract = next(iter(convert.CONTRACTS.values()))
    source = save(tmp_path / "source.csv", contract, [row_for(contract, "")])
    row = next(convert.records(source, contract))
    assert row["candidate_name"] is None
    assert row["candidate_missing"] is True


def test_failure_after_first_batch_preserves_previous_release(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "BATCH_SIZE", 1)
    contract = next(iter(convert.CONTRACTS.values()))
    source = save(tmp_path / "source.csv", contract, [row_for(contract), ["broken"]])
    target = tmp_path / "release.parquet"
    target.write_bytes(b"previous")
    with pytest.raises(ValueError, match="column count"):
        convert.convert(source, target, contract)
    assert target.read_bytes() == b"previous"
    assert not target.with_suffix(".parquet.part").exists()


def test_check_rejects_extra_saved_rows(tmp_path):
    contract = next(iter(convert.CONTRACTS.values()))
    source = save(
        tmp_path / "source.csv",
        contract,
        [row_for(contract), row_for(contract, "Other")],
    )
    target = tmp_path / "release.parquet"
    convert.convert(source, target, contract)
    save(source, contract, [row_for(contract)])
    with pytest.raises(ValueError, match=r"rows differ|extra rows"):
        convert.convert(source, target, contract, check=True)

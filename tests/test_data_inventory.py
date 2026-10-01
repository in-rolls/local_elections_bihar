import csv
import gzip
import hashlib

import pytest
from data_inventory import read_inventory, summary, verify


def receipt(tmp_path, rows):
    target = tmp_path / "inventory.csv.gz"
    with gzip.open(target, "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return target


def test_verify_detects_same_size_corruption_and_missing_drive(tmp_path):
    folder = tmp_path / "data/2011/raw/source"
    folder.mkdir(parents=True)
    path = folder / "a.pdf"
    path.write_bytes(b"original")
    rows = [
        {
            "canonical_path": str(path.relative_to(tmp_path)),
            "bytes": 8,
            "sha256": hashlib.sha256(b"original").hexdigest(),
        }
    ]
    records = read_inventory(receipt(tmp_path, rows))
    verify(tmp_path, records)
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="checksum differs"):
        verify(tmp_path, records)
    path.unlink()
    with pytest.raises(ValueError, match="unavailable"):
        verify(tmp_path, records)


def test_duplicate_receipts_count_once_and_conflicts_fail(tmp_path):
    row = {
        "canonical_path": "data/2021/interim/archive/a.tar",
        "bytes": 123,
        "sha256": "a" * 64,
    }
    records = read_inventory(receipt(tmp_path, [row, row]))
    assert len(records) == 1
    out = tmp_path / "catalog.csv"
    summary(records, out)
    with out.open() as handle:
        result = list(csv.DictReader(handle))
    assert result[0]["bytes"] == result[0]["archive_bytes"] == "123"
    assert result[0]["files"] == "1"
    with pytest.raises(ValueError, match="Conflicting"):
        read_inventory(receipt(tmp_path, [row, {**row, "sha256": "b" * 64}]))


@pytest.mark.parametrize("path", ["/tmp/x", "data/../secret", "data/2011/table"])
def test_inventory_rejects_paths_outside_asset_roots(tmp_path, path):
    with pytest.raises(ValueError, match="inventory"):
        read_inventory(
            receipt(
                tmp_path, [{"canonical_path": path, "bytes": 1, "sha256": "a" * 64}]
            )
        )


def test_pruned_files_are_excluded_only_when_receipt_matches(tmp_path):
    row = {
        "canonical_path": "data/2016/interim/archive/a.tar",
        "bytes": 123,
        "sha256": "a" * 64,
    }
    inventory = receipt(tmp_path, [row])
    pruning = tmp_path / "pruning.csv.gz"
    pruning.write_bytes(inventory.read_bytes())
    assert read_inventory(inventory, pruning) == {}
    receipt(tmp_path, [{**row, "sha256": "b" * 64}])
    with pytest.raises(ValueError, match="Pruning receipt mismatch"):
        read_inventory(inventory, pruning)

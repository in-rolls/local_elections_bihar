import pytest

from scripts.reporting.storage import SOURCE_YEARS, asset_summary


def storage(tmp_path):
    for year in SOURCE_YEARS:
        (tmp_path / year / "raw").mkdir(parents=True)
    return tmp_path


def test_scan_counts_actual_files_and_ignores_mac_metadata(tmp_path):
    data = storage(tmp_path)
    bundle = data / "2011/raw/reports"
    bundle.mkdir()
    (bundle / "report.pdf").write_bytes(b"source")
    (bundle / "._report.pdf").write_bytes(b"metadata")
    (bundle / ".DS_Store").write_bytes(b"metadata")
    working = data / "2021/interim"
    working.mkdir()
    (working / "receipt.json").write_bytes(b"{}")
    rows = asset_summary(data)
    assert rows == [
        {"path": "2011/raw/reports", "files": 1, "bytes": 6, "formats": [".pdf"]},
        {
            "path": "2021/interim/receipt.json",
            "files": 1,
            "bytes": 2,
            "formats": [".json"],
        },
    ]


def test_unmounted_source_drive_is_not_reported_as_zero(tmp_path):
    data = storage(tmp_path)
    raw = data / "2011/raw"
    raw.rmdir()
    raw.symlink_to(tmp_path / "unmounted")
    with pytest.raises(ValueError, match="Storage unavailable"):
        asset_summary(data)


def test_links_within_collection_cannot_duplicate_sizes_or_recurse(tmp_path):
    data = storage(tmp_path)
    (data / "2011/raw/loop").symlink_to(data / "2011/raw")
    with pytest.raises(ValueError, match="Unexpected link"):
        asset_summary(data)

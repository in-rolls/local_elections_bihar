"""Consolidated metadata must still describe and fingerprint the actual data."""

import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest


@pytest.mark.parametrize(
    "folder",
    [
        "release/2016",
        "release/2016/winner_list",
        "release/2021",
        "release/2011/gaya_mukhiya",
        "release/2011/mukhiya_reports",
        "release/2011/khajuria_judgment",
        "release/2021/reservation_check",
    ],
)
def test_manifest_covers_files_and_columns(folder):
    root = Path("data") / folder
    manifest = json.loads((root / "MANIFEST.json").read_text())
    files = manifest["files"]
    if isinstance(files, dict):
        files = [
            {"path": name, **({"sha256": info} if isinstance(info, str) else info)}
            for name, info in files.items()
        ]
    for info in files:
        path = root / info["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == info["sha256"]
        if path.suffix != ".parquet":
            continue
        schema = pq.read_schema(path)
        if "columns" in info:
            columns = info["columns"]
        elif folder.endswith("gaya_mukhiya"):
            columns = manifest["columns"][path.name]
        else:
            columns = manifest["columns"]
        assert set(columns) == set(schema.names)
        assert all(spec["type"] and spec["description"] for spec in columns.values())
        if "rows" in info:
            assert pq.read_metadata(path).num_rows == info["rows"]


def test_urban_receipts_retain_source_provenance():
    from local_elections_bihar.build.fetch_log import rows

    records = {row["path"]: row for row in rows()}
    for path in [
        "data/raw/urban/patna/winners_2022.json",
        "data/raw/urban_expansion/urban_women_2007_rcues.pdf",
    ]:
        row = records[path]
        assert row["url"].startswith("http")
        assert row["fetched_at_utc"]
        assert row["method"] == "live"
        assert row["sha256"] == hashlib.sha256(Path(path).read_bytes()).hexdigest()

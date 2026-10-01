"""Consolidated metadata must still describe and fingerprint the actual data."""

import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest


@pytest.mark.parametrize(
    "folder",
    [
        "2016",
        "2021",
        "2011/gaya_mukhiya",
        "2011/mukhiya_reports",
        "2011/khajuria_judgment",
        "2021/reservation_check",
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

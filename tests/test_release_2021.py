import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from release_2021 import sha, verify


def test_statewide_release_reconciles():
    verify(Path("data/release/2021"))


def test_release_rejects_modified_values(tmp_path):
    import shutil

    source = Path("data/release/2021")
    for name in ["MANIFEST.json", "gp_head_candidates_2021.parquet"]:
        shutil.copyfile(source / name, tmp_path / name)
    path = tmp_path / "gp_head_candidates_2021.parquet"
    table = pq.read_table(path)
    column = table.column_names.index("elected")
    table = table.set_column(column, "elected", pa.array([False] * len(table)))
    pq.write_table(table, path)
    with pytest.raises(ValueError, match="checksum"):
        verify(tmp_path)


def test_release_rejects_duplicates_even_with_updated_manifest(tmp_path):
    import shutil

    source = Path("data/release/2021")
    for path in source.glob("*.parquet"):
        shutil.copyfile(path, tmp_path / path.name)
    manifest = json.loads((source / "MANIFEST.json").read_text())
    path = tmp_path / "gp_head_candidates_2021.parquet"
    table = pq.read_table(path)
    pq.write_table(pa.concat_tables([table, table.slice(0, 1)]), path)
    info = next(x for x in manifest["files"] if x["path"] == path.name)
    info.update(sha256=sha(path), rows=info["rows"] + 1)
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Duplicate release key"):
        verify(tmp_path)


def test_published_source_archive_checksum():
    root = Path("data/raw")
    metadata = json.loads((root / "statewide_2021_archive.json").read_text())
    path = root / metadata["archive"]
    assert path.stat().st_size == metadata["bytes"]
    assert sha(path) == metadata["sha256"]

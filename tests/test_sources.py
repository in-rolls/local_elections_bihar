"""Source handling must preserve originals and never fetch during offline parsing."""

import base64
import gzip
import json
import zipfile
from pathlib import Path

import pytest

from local_elections_bihar.shared.portal import read_saved
from local_elections_bihar.sources import digest, extract, fetch, pack


def test_saved_response_missing_or_incomplete_is_not_a_download(tmp_path):
    for content in [None, b"truncated"]:
        path = tmp_path / "missing.jsonl.gz"
        if content:
            path.write_bytes(content)
        with pytest.raises(FileNotFoundError, match="Missing or incomplete"):
            read_saved(tmp_path, "missing", "Result")


def test_saved_request_identity_is_checked(tmp_path):
    events = [
        {
            "ok": True,
            "page": "Result",
            "params": {"districtId": 1},
            "body_base64": base64.b64encode(b"[]").decode(),
        },
        {"done": True},
    ]
    (tmp_path / "one.jsonl.gz").write_bytes(
        gzip.compress("\n".join(map(json.dumps, events)).encode())
    )
    assert read_saved(tmp_path, "one", "Result", {"districtId": "1"}) == b"[]"
    with pytest.raises(ValueError, match="differs"):
        read_saved(tmp_path, "one", "Result", {"districtId": 2})


@pytest.mark.parametrize(
    "name", ["../escape", "/absolute", "2021/raw/wrong", "2011/raw/../../escape"]
)
def test_unsafe_archive_writes_nothing(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("2011/raw/good.pdf", b"good")
        out.writestr(name, b"bad")
    data = tmp_path / "data"
    with pytest.raises(ValueError, match="Unsafe"):
        extract(archive, data, "2011")
    assert not data.exists()


def test_fetch_rejects_corruption_before_extraction(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("2011/raw/original.pdf", b"original")
    spec = {
        "archives": {
            "2011": [
                {
                    "url": archive.as_uri(),
                    "bytes": archive.stat().st_size,
                    "sha256": "0" * 64,
                }
            ]
        }
    }
    data = tmp_path / "data"
    with pytest.raises(ValueError, match="checksum"):
        fetch(spec, "2011", data)
    assert not list(data.iterdir())
    spec["archives"]["2011"][0]["sha256"] = digest(archive)
    fetch(spec, "2011", data)
    assert (data / "2011/raw/original.pdf").read_bytes() == b"original"
    fetch(spec, "2011", data)
    (data / "2011/raw/original.pdf").write_bytes(b"different")
    with pytest.raises(FileExistsError):
        fetch(spec, "2011", data)


def test_pack_contains_selected_originals_only(tmp_path):
    data = tmp_path / "data"
    root = data / "2011/raw/reports"
    root.mkdir(parents=True)
    (root / "original.pdf").write_bytes(b"source")
    (root / "intermediate.parquet").write_bytes(b"derived")
    (root / "._original.pdf").write_bytes(b"mac metadata")
    spec = {
        "pipelines": {"2011": {"inputs": ["reports"]}},
        "source_groups": {
            "reports": {"root": "2011/raw/reports", "include": ["*.pdf"]}
        },
    }
    destination = tmp_path / "archives"
    info = pack(spec, "2011", data, destination)[0]
    assert info["source_files"] == 1
    with zipfile.ZipFile(destination / info["filename"]) as archive:
        assert archive.namelist() == ["2011/raw/reports/original.pdf"]
        assert archive.read(archive.namelist()[0]) == b"source"


def test_archive_cannot_write_through_existing_symlink(tmp_path):
    data = tmp_path / "data"
    (data / "2011").mkdir(parents=True)
    (data / "2011/raw").symlink_to(tmp_path / "elsewhere")
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("2011/raw/source.pdf", b"original")
    with pytest.raises(ValueError, match="symlink"):
        extract(archive, data, "2011")


def test_declared_outputs_match_public_contract():
    spec = json.loads(Path("data/PROVENANCE.json").read_text())
    outputs = [f for p in spec["pipelines"].values() for f in p["outputs"]]
    assert len(outputs) == len(set(outputs)) == 16
    assert all((Path("data") / f).is_file() for f in outputs)
    assert all(
        p["outputs"]
        == [f for s in p["steps"] for f in s["produces"] if not f.startswith("{cache}")]
        for p in spec["pipelines"].values()
    )


def test_district_archives_partition_and_resume(tmp_path):
    data = tmp_path / "originals"
    root = data / "2016/raw/results"
    root.mkdir(parents=True)
    for district in [1, 2]:
        (root / f"office_d{district:02}.jsonl.gz").write_bytes(bytes([district]))
    spec = {
        "pipelines": {"2016": {"inputs": ["pages"]}},
        "source_groups": {"pages": {"root": "2016/raw/results", "include": ["*"]}},
        "archives": {
            "2016": [
                {"filename": "d01.zip", "include": ["*_d01*"]},
                {"filename": "d02.zip", "include": ["*_d02*"]},
            ]
        },
    }
    destination = tmp_path / "archives"
    receipts = pack(spec, "2016", data, destination)
    assert sum(r["source_files"] for r in receipts) == 2
    for receipt in receipts:
        receipt["url"] = (destination / receipt["filename"]).as_uri()
    spec["archives"]["2016"] = receipts
    restored = tmp_path / "restored"
    actual = receipts[1]["sha256"]
    receipts[1]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        fetch(spec, "2016", restored)
    assert (restored / "2016/raw/results/office_d01.jsonl.gz").read_bytes() == b"\x01"
    assert not (restored / "2016/raw/results/office_d02.jsonl.gz").exists()
    receipts[1]["sha256"] = actual
    fetch(spec, "2016", restored)
    assert (restored / "2016/raw/results/office_d02.jsonl.gz").read_bytes() == b"\x02"
    receipts[0]["include"] = ["*"]
    with pytest.raises(ValueError, match="exactly one"):
        pack(spec, "2016", data, tmp_path / "overlap")
    receipts[0]["include"] = ["*missing*"]
    with pytest.raises(ValueError, match="exactly one"):
        pack(spec, "2016", data, tmp_path / "omitted")

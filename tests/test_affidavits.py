import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from affidavits import frame, page_score


def test_frame_uses_result_flag_and_full_geography(tmp_path):
    rows = []
    for panchayat in [11, 12]:
        for kind in ["candidates", "results"]:
            rows.append(
                {
                    "district_id": 1,
                    "block_id": 2,
                    "panchayat_id": panchayat,
                    "candidate_serial": 1,
                    "kind": kind,
                    "year": 2021,
                    "post_id": 3,
                    "candidate_name": "Synthetic (विजेता)"
                    if kind == "results"
                    else "Synthetic",
                    "elected": True if kind == "results" else None,
                    "candidate_gender": "महिला",
                    "candidate_age": 30,
                    "affidavit_url": "https://example.test/a.pdf",
                    "source_url": "https://example.test/source",
                }
            )
    source, output = tmp_path / "source.parquet", tmp_path / "frame.parquet"
    pq.write_table(pa.Table.from_pylist(rows), source)
    frame(source, output)
    got = pq.read_table(output).to_pylist()
    assert len(got) == 2
    assert all(r["name_matches"] for r in got)
    assert len({r["document_id"] for r in got}) == 2
    rows.append(rows[0])
    pq.write_table(pa.Table.from_pylist(rows), source)
    with pytest.raises(ValueError, match="Duplicate"):
        frame(source, output)


def test_page_locator_does_not_assign_education_values():
    assert page_score("Educational Qualification: unreadable") >= 4
    assert page_score("शैक्षणिक योग्यता") >= 4
    assert page_score("Income certificate") == 0


def test_reviews_preserve_unknowns_and_reject_proposer_education(tmp_path):
    import csv

    from affidavits import read_reviews

    row = {
        "document_id": "a",
        "page": "2",
        "graduate_plus": "",
        "illiterate": "0",
        "prior_elected": "",
        "quota_document": "1",
        "education_category": "unspecified_educated",
        "review_status": "visually_checked",
        "page_kind": "candidate_biography",
        "additional_pages": "3;4",
    }
    path = tmp_path / "reviews.csv"

    def write(rows):
        with path.open("w") as f:
            writer = csv.DictWriter(f, fieldnames=list(row))
            writer.writeheader()
            writer.writerows(rows)

    write([row])
    got = read_reviews(path, ["a"])["a"]
    assert got["graduate_plus"] is None
    assert got["illiterate"] == 0
    assert got["additional_pages"] == [3, 4]
    write([row, row])
    with pytest.raises(ValueError, match="Duplicate"):
        read_reviews(path, ["a"])
    write([row])
    with pytest.raises(ValueError, match="every frame document"):
        read_reviews(path, ["a", "b"])
    write([{**row, "graduate_plus": "0"}])
    with pytest.raises(ValueError, match="Unresolved"):
        read_reviews(path, ["a"])
    write([{**row, "page_kind": "proposer_biography"}])
    with pytest.raises(ValueError, match="Non-candidate"):
        read_reviews(path, ["a"])
    write([{**row, "quota_document": "2"}])
    with pytest.raises(ValueError, match="Invalid binary"):
        read_reviews(path, ["a"])


def test_frame_rejects_undated_or_different_office_records(tmp_path):
    source, output = tmp_path / "source.parquet", tmp_path / "frame.parquet"
    for row in [{"year": None, "post_id": 3}, {"year": 2021, "post_id": 1}]:
        pq.write_table(pa.Table.from_pylist([row]), source)
        with pytest.raises(ValueError, match="explicitly dated"):
            frame(source, output)


def test_published_education_matches_reviews_and_source_artifacts():
    import json
    from pathlib import Path

    from affidavits import file_hash, read_reviews

    root = Path(__file__).resolve().parents[1] / "data/fin/2021"
    manifest = json.loads((root / "education.json").read_text())
    assert file_hash(root / "education.parquet") == manifest["output_sha256"]
    assert file_hash(root / "education.csv") == manifest["csv_sha256"]
    assert file_hash(root / "affidavit_frame.parquet") == manifest["frame_sha256"]
    assert file_hash(root / "education_review.csv") == manifest["review_sha256"]
    frame_rows = pq.read_table(root / "affidavit_frame.parquet").to_pylist()
    rows = pq.read_table(root / "education.parquet").to_pylist()
    assert len(rows) == len(frame_rows) == manifest["rows"]
    assert {r["document_id"] for r in rows} == {r["document_id"] for r in frame_rows}
    reviews = read_reviews(root / "education_review.csv", list(manifest["documents"]))
    for row in rows:
        doc = manifest["documents"][row["document_id"]]
        assert row["document_sha256"] == doc["sha256"]
        assert row["affidavit_url"] == doc["url"]
        assert 1 <= row["page"] <= doc["pages"]
        assert row["source_page_url"] == f"{doc['url']}#page={row['page']}"
        for key, value in reviews[row["document_id"]].items():
            assert row[key] == value
    for artifact, checksum in manifest["page_artifact_sha256"].items():
        assert file_hash(root / artifact) == checksum
    assert manifest["degree_classified"] == sum(
        r["graduate_plus"] is not None for r in rows
    )


def test_changed_pdf_invalidates_cached_ocr(tmp_path, monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace

    import affidavits

    monkeypatch.setattr(affidavits, "ROOT", tmp_path)
    folder = tmp_path / "a"
    folder.mkdir()
    source = folder / "source.pdf"
    source.write_bytes(b"%PDF-old")
    (folder / "download.json").write_text(
        json.dumps({"url": "https://example.test/old", "sha256": "old"})
    )
    for filename in ["page_01.txt", "page_01.png", "pages.json"]:
        (folder / filename).write_text("stale")
    response = SimpleNamespace(
        status_code=200,
        content=b"%PDF-new",
        raise_for_status=lambda: None,
    )
    monkeypatch.setattr(
        affidavits,
        "LOCAL",
        SimpleNamespace(session=SimpleNamespace(get=lambda *args, **kwargs: response)),
    )
    monkeypatch.setattr(affidavits, "pdf_pages", lambda path: 2)
    row = {"document_id": "a", "affidavit_url": "https://example.test/new"}
    metadata = affidavits.download(row)
    assert metadata["sha256"] == hashlib.sha256(b"%PDF-new").hexdigest()
    assert metadata["pages"] == 2
    assert metadata["ok"] is True
    assert not list(folder.glob("page_*"))
    assert not (folder / "pages.json").exists()
    assert affidavits.download(row)["sha256"] == metadata["sha256"]


def test_download_status_preserves_pending_failed_and_corrupt_files(
    tmp_path, monkeypatch
):
    import json

    import affidavits

    monkeypatch.setattr(affidavits, "ROOT", tmp_path / "pdfs")
    rows = [
        {
            **dict(zip(affidavits.KEY, [1, 2, p, 1], strict=True)),
            "document_id": str(p),
            "affidavit_url": "https://example.test/file.pdf",
        }
        for p in range(3)
    ]
    for row in rows[1:]:
        folder = affidavits.ROOT / row["document_id"]
        folder.mkdir(parents=True)
        (folder / "failure.json").write_text(json.dumps({"reason": "invalid PDF"}))
    folder = affidavits.ROOT / "2"
    (folder / "source.pdf").write_bytes(b"corrupt")
    (folder / "download.json").write_text(
        json.dumps(
            {"ok": True, "url": rows[2]["affidavit_url"], "bytes": 100, "sha256": "x"}
        )
    )
    out = tmp_path / "status.parquet"
    summary = affidavits.download_status(rows, out)
    assert summary["pending"] == 1 and summary["failed"] == 2
    assert summary["downloaded"] == 0
    assert pq.read_table(out).num_rows == 3


def test_downloader_continues_after_source_failure(tmp_path, monkeypatch):
    import affidavits

    monkeypatch.setattr(affidavits, "ROOT", tmp_path / "pdfs")
    seen = []
    rows = [
        {
            **dict(zip(affidavits.KEY, [1, 2, p, 1], strict=True)),
            "document_id": str(p),
            "affidavit_url": "https://example.test/file.pdf",
        }
        for p in range(3)
    ]

    def download(row):
        seen.append(row["document_id"])
        if row["document_id"] == "1":
            raise ValueError("bad PDF")

    monkeypatch.setattr(affidavits, "download", download)
    affidavits.download_all(rows, 1, tmp_path / "status.parquet")
    assert seen == ["0", "1", "2"]
    assert (affidavits.ROOT / "1/failure.json").exists()

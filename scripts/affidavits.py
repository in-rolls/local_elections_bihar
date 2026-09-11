"""Download confirmed 2021 winners' affidavits and locate education pages."""

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from PIL import Image
from sec_portal import TransientError, retry_after, retry_wait
from tenacity import Retrying, retry_if_exception_type, stop_after_delay

LOCAL = threading.local()
KEY = ["district_id", "block_id", "panchayat_id", "candidate_serial"]
ROOT = Path("data/derived/affidavits_2021")


def frame(source, out):
    records = pq.read_table(source).to_pylist()
    if not records or any(r["year"] != 2021 or r["post_id"] != 3 for r in records):
        raise ValueError("Expected explicitly dated 2021 mukhiya records")
    candidates = {}
    for row in records:
        if row["kind"] != "candidates":
            continue
        key = tuple(row[k] for k in KEY)
        if key in candidates:
            raise ValueError("Duplicate candidate key")
        candidates[key] = row
    winners = []
    for row in records:
        if row["kind"] != "results" or row["elected"] is not True:
            continue
        key = tuple(row[k] for k in KEY)
        candidate = candidates[key]
        name = re.sub(r"\s*\(विजेता\)\s*$", "", row["candidate_name"]).strip()
        document_id = "_".join(str(v) for v in key)
        winners.append(
            {
                **{k: row[k] for k in KEY},
                "document_id": document_id,
                "year": 2021,
                "post_id": 3,
                "candidate_name": candidate["candidate_name"],
                "result_name": row["candidate_name"],
                "name_matches": name == candidate["candidate_name"].strip(),
                "candidate_gender": candidate["candidate_gender"],
                "candidate_age": candidate["candidate_age"],
                "affidavit_url": candidate["affidavit_url"],
                "candidate_source_url": candidate["source_url"],
                "result_source_url": row["source_url"],
            }
        )
    if len({tuple(w[k] for k in KEY[:-1]) for w in winners}) != len(winners):
        raise ValueError("Multiple winners for a seat")
    if not winners:
        raise ValueError("No confirmed winners")
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(winners), out, compression="zstd")
    print(
        json.dumps(
            {
                "winners": len(winners),
                "name_review": sum(not w["name_matches"] for w in winners),
            }
        )
    )


def download(row):
    folder = ROOT / row["document_id"]
    folder.mkdir(parents=True, exist_ok=True)
    target, meta = folder / "source.pdf", folder / "download.json"
    if target.exists() and meta.exists():
        saved = json.loads(meta.read_text())
        if (
            saved["url"] == row["affidavit_url"]
            and saved["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
        ):
            return saved
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        LOCAL.session.headers["User-Agent"] = "local-elections-bihar research archive"

    def attempt():
        start = time.monotonic()
        event = {
            "url": row["affidavit_url"],
            "fetched_at": datetime.now(UTC).isoformat(),
            "ok": False,
        }
        try:
            r = LOCAL.session.get(row["affidavit_url"], timeout=(30, 180))
            event["status"] = r.status_code
            if r.status_code == 429 or r.status_code >= 500:
                raise TransientError(
                    str(r.status_code), retry_after(r.headers.get("Retry-After"))
                )
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                (folder / "unexpected_response.bin").write_bytes(r.content)
                raise ValueError("Affidavit response is not a PDF")
            event.update(
                sha256=hashlib.sha256(r.content).hexdigest(),
                bytes=len(r.content),
            )
            part = target.with_suffix(".part")
            part.write_bytes(r.content)
            event["pages"] = pdf_pages(part)
            if target.exists() and file_hash(target) != event["sha256"]:
                for pattern in ["page_*.txt", "page_*.png", "pages.json"]:
                    for cached in folder.glob(pattern):
                        cached.unlink()
            part.replace(target)
            event["ok"] = True
            meta.write_text(json.dumps(event, indent=2) + "\n")
            return event
        except (requests.RequestException, ValueError, TransientError) as error:
            event["reason"] = str(error)
            raise
        finally:
            event["seconds"] = time.monotonic() - start
            with (folder / "requests.jsonl").open("a") as log:
                log.write(json.dumps(event) + "\n")

    return Retrying(
        retry=retry_if_exception_type(
            (requests.ConnectionError, requests.Timeout, TransientError)
        ),
        stop=stop_after_delay(7200),
        wait=retry_wait,
        reraise=True,
    )(attempt)


def page_score(text):
    lower = text.lower()
    return (
        4 * bool(re.search(r"educ\w*|qualific\w*|शैक्ष|शैक्षणिक", lower))
        + 2 * bool(re.search(r"bio\s*[- ]?\s*data|candidate", lower))
        + bool(re.search(r"profession|elected|married", lower))
    )


def pdf_pages(path):
    result = subprocess.run(
        ["pdfinfo", str(path)], capture_output=True, text=True, check=True, timeout=30
    )
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
    if match is None or int(match[1]) < 1:
        raise ValueError("PDF has no readable page count")
    return int(match[1])


def render_page(source, page, prefix, dpi=110):
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(page),
            "-l",
            str(page),
            "-r",
            str(dpi),
            "-gray",
            "-png",
            "-singlefile",
            str(source),
            str(prefix),
        ],
        capture_output=True,
        check=True,
        timeout=60,
    )
    return prefix.with_suffix(".png")


def locate(row):
    folder = ROOT / row["document_id"]
    output = folder / "pages.json"
    if output.exists() and all(
        "rotation_checked" in x for x in json.loads(output.read_text())
    ):
        return json.loads(output.read_text())
    count = pdf_pages(folder / "source.pdf")
    info = subprocess.run(
        ["pdfinfo", "-f", "1", "-l", str(count), str(folder / "source.pdf")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    sizes = {
        int(n): (float(w), float(h))
        for n, w, h in re.findall(r"Page\s+(\d+) size:\s+([\d.]+) x ([\d.]+)", info)
    }
    embedded = subprocess.run(
        ["pdftotext", "-layout", str(folder / "source.pdf"), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\f")
    found = []
    for page in range(1, pdf_pages(folder / "source.pdf") + 1):
        target = folder / f"page_{page:02d}.txt"
        if not target.exists():
            image = render_page(folder / "source.pdf", page, folder / "ocr_page")
            result = subprocess.run(
                ["tesseract", str(image), "stdout", "-l", "eng+hin", "--psm", "11"],
                capture_output=True,
                check=True,
                env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                timeout=90,
            )
            target.write_text(result.stdout.decode())
            image.unlink()
        score = page_score(target.read_text())
        embedded_score = page_score(embedded[page - 1]) if page <= len(embedded) else 0
        rotation = 0
        if score < 4 and sizes.get(page, (0, 1))[0] > sizes.get(page, (0, 1))[1]:
            image = render_page(
                folder / "source.pdf", page, folder / "orientation_page"
            )
            with Image.open(image) as original:
                for angle in [-90, 90]:
                    rotated = folder / "rotated.png"
                    original.rotate(angle, expand=True).save(rotated)
                    result = subprocess.run(
                        [
                            "tesseract",
                            str(rotated),
                            "stdout",
                            "-l",
                            "eng+hin",
                            "--psm",
                            "11",
                        ],
                        capture_output=True,
                        check=True,
                        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                        timeout=90,
                    )
                    text = result.stdout.decode()
                    (folder / f"page_{page:02d}_rotation_{angle}.txt").write_text(text)
                    if page_score(text) > score:
                        score, rotation = page_score(text), angle
                    rotated.unlink()
            image.unlink()
        found.append(
            {
                "page": page,
                "score": score,
                "embedded_score": embedded_score,
                "rotation": rotation,
                "rotation_checked": True,
            }
        )
    selected = [x for x in found if max(x["score"], x["embedded_score"]) >= 4]
    for item in selected:
        image = render_page(
            folder / "source.pdf",
            item["page"],
            folder / f"page_{item['page']:02d}",
            dpi=140,
        )
        if item["rotation"]:
            with Image.open(image) as original:
                original.rotate(item["rotation"], expand=True).save(image)
    output.write_text(json.dumps(found, indent=2) + "\n")
    return {
        "document_id": row["document_id"],
        "pages": len(found),
        "matches": [x for x in found if x["score"] >= 4],
    }


BINARY = ["graduate_plus", "illiterate", "prior_elected", "quota_document"]


def read_reviews(path, ids):
    with path.open() as source:
        rows = list(csv.DictReader(source))
    if len({r["document_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate review document")
    if {r["document_id"] for r in rows} != set(ids):
        raise ValueError("Review must cover every frame document exactly once")
    for row in rows:
        row["page"] = int(row["page"])
        for field in BINARY:
            if row[field] not in {"", "0", "1"}:
                raise ValueError(f"Invalid binary value: {field}")
            row[field] = int(row[field]) if row[field] else None
        if row["review_status"] not in {
            "visually_checked",
            "needs_review",
            "source_missing",
        }:
            raise ValueError("Invalid review status")
        if row["page_kind"] not in {
            "candidate_biography",
            "candidate_affidavit",
            "fee_receipt",
            "proposer_biography",
        }:
            raise ValueError("Invalid page kind")
        if row["page_kind"] in {"fee_receipt", "proposer_biography"} and any(
            row[f] is not None for f in BINARY[:3]
        ):
            raise ValueError("Non-candidate page cannot supply elite attributes")
        if (
            row["education_category"]
            in {
                "ambiguous",
                "missing_document",
                "not_stated",
                "school_only",
                "unspecified_educated",
            }
            and row["graduate_plus"] is not None
        ):
            raise ValueError("Unresolved qualification must not assign degree status")
        row["additional_pages"] = [
            int(p) for p in row["additional_pages"].split(";") if p
        ]
    return {r["document_id"]: r for r in rows}


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(frame_path, review_path, out):
    frame_rows = pq.read_table(frame_path).to_pylist()
    ids = [r["document_id"] for r in frame_rows]
    if len(set(ids)) != len(ids) or not ids:
        raise ValueError("Empty or duplicate affidavit frame")
    reviews = read_reviews(review_path, ids)
    rows, documents, artifacts = [], {}, {}
    pages_out = out.parent / "education_pages"
    pages_out.mkdir(parents=True, exist_ok=True)
    for row in frame_rows:
        doc = row["document_id"]
        folder = ROOT / doc
        meta = json.loads((folder / "download.json").read_text())
        if meta["url"] != row["affidavit_url"] or meta["sha256"] != file_hash(
            folder / "source.pdf"
        ):
            raise ValueError(f"Source mismatch: {doc}")
        review = reviews[doc]
        page = review["page"]
        for selected in [page, *review["additional_pages"]]:
            if not 1 <= selected <= meta["pages"]:
                raise ValueError(f"Review page outside document: {doc}")
            target = pages_out / f"{doc}_p{selected:02d}.png"
            shutil.copyfile(folder / f"page_{selected:02d}.png", target)
            artifacts[str(target.relative_to(out.parent))] = file_hash(target)
        scores = json.loads((folder / "pages.json").read_text())
        selected = [
            s["page"]
            for s in scores
            if max(s["score"], s.get("embedded_score", 0)) >= 4
        ]
        rows.append(
            {
                **row,
                **review,
                "review_method": "Codex visual transcription; no second reviewer",
                "document_sha256": meta["sha256"],
                "document_fetched_at": meta["fetched_at"],
                "source_page_url": f"{row['affidavit_url']}#page={page}",
                "page_artifact": f"education_pages/{doc}_p{page:02d}.png",
                "locator_selected_review_page": page in selected,
            }
        )
        documents[doc] = meta
    table = pa.Table.from_pylist(rows)
    for field in BINARY:
        table = table.set_column(
            table.schema.get_field_index(field),
            field,
            pa.array([r[field] for r in rows], type=pa.int8()),
        )
    pq.write_table(table, out, compression="zstd")
    with out.with_suffix(".csv").open("w") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=table.column_names, lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "additional_pages": ";".join(map(str, row["additional_pages"])),
                }
            )
    coverage = []
    for quota in [0, 1, None]:
        group = [r for r in rows if r["quota_document"] == quota]
        coverage.append(
            {
                "quota_document": quota,
                "winners": len(group),
                "degree_classified": sum(r["graduate_plus"] is not None for r in group),
            }
        )
    manifest = {
        "frame_sha256": file_hash(frame_path),
        "review_sha256": file_hash(review_path),
        "output_sha256": file_hash(out),
        "csv_sha256": file_hash(out.with_suffix(".csv")),
        "rows": len(rows),
        "degree_classified": sum(r["graduate_plus"] is not None for r in rows),
        "quota_classified": sum(r["quota_document"] is not None for r in rows),
        "coverage_by_document_reservation": coverage,
        "review_method": (
            "Codex inspected candidate biographies and affidavits; "
            "no independent second coding. Coverage is not an accuracy estimate."
        ),
        "locator": (
            "Tesseract eng+hin, psm 11, 110 dpi; embedded text and "
            "landscape rotation fallback; qualifications are visually transcribed, "
            "not OCR parsed."
        ),
        "schema": {f.name: str(f.type) for f in table.schema},
        "documents": documents,
        "page_artifact_sha256": artifacts,
    }
    out.with_suffix(".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                k: manifest[k]
                for k in [
                    "rows",
                    "degree_classified",
                    "quota_classified",
                    "coverage_by_document_reservation",
                ]
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["frame", "download", "locate", "export"])
    parser.add_argument(
        "--frame", type=Path, default=Path("data/fin/2021/affidavit_frame.parquet")
    )
    parser.add_argument(
        "--source", type=Path, default=Path("data/fin/2021/mukhiya_2021.parquet")
    )
    parser.add_argument(
        "--review", type=Path, default=Path("data/fin/2021/education_review.csv")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("data/fin/2021/education.parquet")
    )
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.stage == "frame":
        frame(args.source, args.frame)
        return
    if args.stage == "export":
        export(args.frame, args.review, args.out)
        return
    rows = pq.read_table(args.frame).to_pylist()
    if args.limit:
        rows = rows[: args.limit]
    operation = download if args.stage == "download" else locate
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(operation, rows):
            print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

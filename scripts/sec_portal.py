"""Archive Bihar SEC's 2021–2026 portal and export winner/reservation records."""

import argparse
import base64
import concurrent.futures
import gzip
import hashlib
import json
import threading
import time
import zlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from bs4 import BeautifulSoup
from tenacity import Retrying, retry_if_exception_type, stop_after_delay

BASE = "https://sec25.bihar.gov.in/sec_new/Panchayat/"
ENDPOINTS = {
    "winners": ("WinningCandidates", "GetWinners"),
    "reservations": ("Reservation", "GetReservations"),
}
LOCAL = threading.local()


class TransientError(Exception):
    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.retry_after = retry_after


def decode_records(body):
    data = json.loads(body)
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValueError("Expected an array of records")
    return data


def completed(path):
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        if len(rows) >= 2 and rows[-1].get("done") and rows[-2].get("ok"):
            return rows[-2]
    except (FileNotFoundError, EOFError, OSError, zlib.error, ValueError):
        pass
    return None


def retry_wait(state):
    error = state.outcome.exception()
    return max(
        getattr(error, "retry_after", 0),
        min(600, 5 * 2 ** min(8, state.attempt_number - 1)),
    )


def retry_after(value):
    if not value:
        return 60
    try:
        return max(0, float(value))
    except ValueError:
        return max(
            0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        )


def fetch(raw, key, page, params=None, *, html=False):
    path = raw / f"{key}.jsonl.gz"
    cached = completed(path)
    if cached:
        if cached["page"] != page or {
            k: str(v) for k, v in (cached["params"] or {}).items()
        } != {k: str(v) for k, v in (params or {}).items()}:
            raise ValueError("Checkpoint request differs from requested unit")
        return base64.b64decode(cached["body_base64"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        LOCAL.session.headers.update(
            {
                "User-Agent": "local-elections-bihar/1.0 public research archive",
                "Referer": BASE + "WinningCandidates",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
    # A new attempt has its own file, so an interrupted gzip tail cannot hide it.
    attempt_path = path.with_suffix(".part")
    if attempt_path.exists():
        stamp = time.time_ns()
        attempt_path.rename(path.with_name(f"{path.stem}.{stamp}.interrupted.gz"))
    with gzip.open(attempt_path, "wt", encoding="utf-8") as stream:

        def attempt():
            event = {
                "fetched_at": datetime.now(UTC).isoformat(),
                "key": key,
                "page": page,
                "params": params,
                "ok": False,
            }
            start = time.monotonic()
            try:
                response = LOCAL.session.get(
                    BASE + page, params=params, timeout=(30, 120)
                )
                event.update(
                    url=response.url,
                    status=response.status_code,
                    body_base64=base64.b64encode(response.content).decode(),
                    content_type=response.headers.get("Content-Type"),
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise TransientError(
                        str(response.status_code),
                        retry_after(response.headers.get("Retry-After")),
                    )
                response.raise_for_status()
                if html:
                    if not BeautifulSoup(response.content, "html.parser").select_one(
                        "#ddlDistrict"
                    ):
                        raise ValueError("Missing district selector")
                else:
                    decode_records(response.content)
                event["ok"] = True
                return response.content
            except (requests.RequestException, ValueError, TransientError) as error:
                event["reason"] = str(error)
                raise
            finally:
                event["seconds"] = time.monotonic() - start
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
                stream.flush()

        policy = Retrying(
            retry=retry_if_exception_type(
                (requests.ConnectionError, requests.Timeout, TransientError)
            ),
            stop=stop_after_delay(7200),
            wait=retry_wait,
            reraise=True,
        )
        body = policy(attempt)
        stream.write(
            json.dumps({"done": True, "fetched_at": datetime.now(UTC).isoformat()})
            + "\n"
        )
    attempt_path.replace(path)
    return body


def enumerate_frame(raw, workers):
    body = fetch(raw, "landing", "WinningCandidates", html=True)
    soup = BeautifulSoup(body, "html.parser")
    districts = [
        (int(o["value"]), o.get_text())
        for o in soup.select("#ddlDistrict option[value]")
        if o["value"]
    ]
    posts = [
        (int(o["value"]), o.get_text())
        for o in soup.select("#ddlPost option[value]")
        if o["value"]
    ]
    if len(districts) != 38 or {p for p, _ in posts} != set(range(1, 7)):
        raise ValueError("District or office enumeration changed")

    def blocks(district):
        code, name = district
        body = fetch(
            raw,
            f"frame/d{code}",
            "WinningCandidates",
            {"handler": "GetBlocks", "districtId": code},
        )
        return [
            {
                "district_id": code,
                "district": name,
                "block_id": b["i"],
                "block": b["n"],
                "post_id": p,
                "post": title,
            }
            for b in decode_records(body)
            for p, title in posts
        ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        rows = [r for group in pool.map(blocks, districts) for r in group]
    if len({(r["district_id"], r["block_id"], r["post_id"]) for r in rows}) != len(
        rows
    ):
        raise ValueError("Repeated geographic unit in frame")
    pq.write_table(
        pa.Table.from_pylist(rows), raw / "frame.parquet", compression="zstd"
    )
    print(
        json.dumps(
            {
                "districts": len(districts),
                "blocks": len(rows) // 6,
                "office_block_units": len(rows),
            }
        ),
        flush=True,
    )


def collect(raw, posts, districts, workers):
    frame = pq.read_table(raw / "frame.parquet").to_pylist()
    units = [
        u
        for u in frame
        if u["post_id"] in posts and (not districts or u["district_id"] in districts)
    ]

    def unit(u):
        d, b, p = u["district_id"], u["block_id"], u["post_id"]
        sizes = {}
        for kind, (page, handler) in ENDPOINTS.items():
            body = fetch(
                raw,
                f"{kind}/d{d}_b{b}_p{p}",
                page,
                {
                    "handler": handler,
                    "PostID": p,
                    "DistrictID": d,
                    "BlockID": b,
                    "PanchayatID": -1,
                },
            )
            sizes[kind] = len(decode_records(body))
        return {"district": d, "block": b, "post": p, "workers": workers, **sizes}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(unit, units):
            print(json.dumps(result), flush=True)


SOURCE_FIELDS = {
    "district": "District",
    "block": "Block",
    "panchayat": "Panchayat",
    "panchayat_id": "PanchayatNo",
    "ward": "WardNo",
    "post": "Post",
    "candidate_name": "CandidateName",
    "candidate_gender": "Gender",
    "candidate_category": "Category",
    "reservation_for_reported": "ReservationFor",
    "reservation_status_reported": "ReservationStatus",
    "seat_reservation": "Reservation",
    "affidavit_url": "Affidavit",
    "photo_url": "CandidatePhotos",
}


def attributes(row):
    result = {
        name: None if row.get(source) is None else str(row[source])
        for name, source in SOURCE_FIELDS.items()
    }
    age = row.get("Age")
    if age is not None and (isinstance(age, bool) or not isinstance(age, int)):
        raise ValueError("Unexpected age type")
    result["candidate_age"] = age
    return result


def parse(raw, out):
    out.mkdir(parents=True, exist_ok=True)
    frame = pq.read_table(raw / "frame.parquet").to_pylist()
    schema = pa.schema(
        [
            ("district_id", pa.int32()),
            ("block_id", pa.int32()),
            ("post_id", pa.int8()),
            ("year", pa.int16()),
            ("source_row", pa.int32()),
            ("source_url", pa.string()),
            ("fetched_at", pa.string()),
            ("source_sha256", pa.string()),
            ("raw_cell", pa.string()),
            ("candidate_age", pa.int32()),
        ]
        + [(name, pa.string()) for name in SOURCE_FIELDS]
    )
    manifest = {
        "election_year": None,
        "portal_window": "2021–2026",
        "files": {},
        "coverage": [],
    }
    for kind in ENDPOINTS:
        output = []
        for u in frame:
            path = (
                raw
                / kind
                / f"d{u['district_id']}_b{u['block_id']}_p{u['post_id']}.jsonl.gz"
            )
            event = completed(path)
            if event is None:
                continue
            body = base64.b64decode(event["body_base64"])
            records = decode_records(body)
            manifest["coverage"].append({**u, "kind": kind, "records": len(records)})
            for i, row in enumerate(records, 1):
                if (
                    int(row["Dist"]) != u["district_id"]
                    or int(row["BlockID"]) != u["block_id"]
                    or row["Post"].strip() != u["post"].strip()
                ):
                    raise ValueError(f"Response outside requested geography: {path}")
                output.append(
                    {
                        "district_id": u["district_id"],
                        "block_id": u["block_id"],
                        "post_id": u["post_id"],
                        "year": None,
                        "source_row": i,
                        "source_url": event["url"],
                        "fetched_at": event["fetched_at"],
                        "source_sha256": hashlib.sha256(body).hexdigest(),
                        "raw_cell": json.dumps(row, ensure_ascii=False),
                        **attributes(row),
                    }
                )
        table = pa.Table.from_pylist(output, schema=schema)
        path = out / f"{kind}.parquet"
        pq.write_table(table, path, compression="zstd")
        manifest["files"][path.name] = {
            "records": len(output),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        print(
            json.dumps(
                {
                    "kind": kind,
                    "records": len(output),
                    "districts": len({r["district_id"] for r in output}),
                    "age_missing": sum(r["candidate_age"] is None for r in output),
                }
            )
        )
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    (out / "SCHEMA.json").write_text(
        json.dumps({f.name: str(f.type) for f in schema}, indent=2) + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["list", "fetch", "parse"])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/portal_2021_2026"))
    parser.add_argument("--out", type=Path, default=Path("data/fin/portal_2021_2026"))
    parser.add_argument("--posts", type=int, nargs="+", default=[3])
    parser.add_argument("--districts", type=int, nargs="+")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.workers < 1 or any(p not in range(1, 7) for p in args.posts):
        parser.error("Positive workers and post IDs 1–6 required")
    if args.stage == "list":
        enumerate_frame(args.raw, args.workers)
    elif args.stage == "fetch":
        collect(args.raw, args.posts, args.districts, args.workers)
    else:
        parse(args.raw, args.out)


if __name__ == "__main__":
    main()

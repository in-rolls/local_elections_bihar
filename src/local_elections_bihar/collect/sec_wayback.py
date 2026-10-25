"""Save the old SEC site's panchayat pages from the Wayback Machine.

    python -m local_elections_bihar.collect.sec_wayback

sec.bih.nic.in, the State Election Commission's site before sec.bihar.gov.in,
published the 2001 panchayat winners (mukhiya by division, pramukh, up-pramukh,
zila parishad chair and vice-chair) and the SEC's January 2006 reservation
directive. The site is gone; the Internet Archive kept it. Captures from May
2006 to 2009 are byte-identical, so the earliest successful capture of each
file is the one kept. The site never linked a list for Bhagalpur division.

Files land under data/raw/sec_bih_nic_in/ at their path on the site. Each
download appends a receipt to data/search_log/sec_bih_nic_in_wayback.jsonl,
which build/fetch_log.py reads.
"""

import datetime as dt
import hashlib
import json
import sys

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from local_elections_bihar.paths import ROOT, SEC_SITE, SEC_SITE_RECEIPTS

HOST = "sec.bih.nic.in"
CDX = "https://web.archive.org/cdx/search/cdx"
PAGES = [
    "mukhiya.html",
    *(
        f"mukhiya/{division}-Mukhiya.pdf"
        for division in (
            "Darbhanga",
            "Koshi",
            "Magadh",
            "Munger",
            "Patna",
            "Purnia",
            "Saran",
            "Tirhut",
        )
    ),
    "pramukh/Pramukh.pdf",
    "pramukh/UP-Pramukh.pdf",
    "pramukh/Zp-Chairman.pdf",
    "pramukh/ZP-VC.pdf",
    "news/reservation.pdf",
]


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(6),
    wait=wait_exponential(min=10, max=120),
)
def get(endpoint, params=None):
    response = requests.get(endpoint, params=params, timeout=120)
    response.raise_for_status()
    return response


def earliest_capture(page):
    rows = get(
        CDX,
        {
            "url": f"{HOST}/{page}",
            "output": "json",
            "fl": "timestamp,original,statuscode,digest",
            "filter": "statuscode:200",
        },
    ).json()
    if len(rows) < 2:
        raise SystemExit(f"no successful capture of {page}")
    return dict(zip(rows[0], min(rows[1:]), strict=True))


def main():
    done = set()
    if SEC_SITE_RECEIPTS.exists():
        done = {
            json.loads(line)["path"]
            for line in SEC_SITE_RECEIPTS.read_text(encoding="utf-8").splitlines()
        }
    SEC_SITE_RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
    for page in PAGES:
        target = SEC_SITE / page
        path = target.relative_to(ROOT).as_posix()
        if path in done:
            continue
        capture = earliest_capture(page)
        url = f"https://web.archive.org/web/{capture['timestamp']}id_/{capture['original']}"
        response = get(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        receipt = {
            "path": path,
            "url": url,
            "original_url": capture["original"],
            "captured_at": capture["timestamp"],
            "fetched_at_utc": dt.datetime.now(dt.UTC).isoformat(),
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "sha256": hashlib.sha256(response.content).hexdigest(),
            "bytes": len(response.content),
        }
        with SEC_SITE_RECEIPTS.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt, ensure_ascii=False) + "\n")
        print(f"{path}: {receipt['bytes']:,} bytes, captured {capture['timestamp']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

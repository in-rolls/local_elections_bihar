"""Save pages of Bihar's old government sites from the Wayback Machine.

    python -m local_elections_bihar.collect.wayback

Two kinds of site, both gone, both kept by the Internet Archive:

- sec.bih.nic.in, the State Election Commission's site before
  sec.bihar.gov.in: the 2001 winner lists (mukhiya by division, pramukh,
  up-pramukh, zila parishad chair and vice-chair) and the SEC's January 2006
  reservation directive. Captures from May 2006 to 2009 are byte-identical.
  The site never linked a list for Bhagalpur division.
- District collectorate sites (<district>.bih.nic.in). Madhubani published
  each block's 2006 result notice (प्रपत्र-23, rule 83): every winner with the
  seat's reservation, mukhiya included.

The earliest successful capture of each page is kept, under
data/raw/<host with _ for .>/ at its path on the site (percent-escapes
decoded). Each download appends a receipt to
data/search_log/<host>_wayback.jsonl, which build/fetch_log.py reads.
"""

import datetime as dt
import hashlib
import json
import sys
import urllib.parse

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from local_elections_bihar.paths import RAW, ROOT, SEARCH_LOG

CDX = "https://web.archive.org/cdx/search/cdx"
SITES = {
    "sec.bih.nic.in": [
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
    ],
    "madhubani.bih.nic.in": [
        "PanchayatElection2006/Andharathadhi%20Panchayat%20Data.pdf",
        "PanchayatElection2006/Babubarhi%20Block%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Basopatti%20panchyat%20data.pdf",
        "PanchayatElection2006/Benipatti%20Panchyat%20Election%20Data.pdf",
        "PanchayatElection2006/Bisfi%20Panchyat%20Data.pdf",
        "PanchayatElection2006/Ghoghardha%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Harlakhi%20Panchyat%20Data.pdf",
        "PanchayatElection2006/Jaynagar%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Jhanjharpur%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Kaluahi%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Khajauli%20Panchayat%20Data.pdf",
        "PanchayatElection2006/Khutauna%20Panchayat%20Data.pdf",
        "PanchayatElection2006/Ladania%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Laknour%20Block%20Panchyat%20Data.pdf",
        "PanchayatElection2006/Laukahi%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Madhepur%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Madhwapur%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Pandaul%20panchyat%20Data.pdf",
        "PanchayatElection2006/Phulparas%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Rahika%20Panchayat%20Data.pdf",
        "PanchayatElection2006/Rajnagar%20Panchyati%20Data.pdf",
        "PanchayatElection2006/Zila%20Parisad%20-Madhubani.pdf",
    ],
}


def folder(host):
    return RAW / host.replace(".", "_")


def receipts(host):
    return SEARCH_LOG / f"{host.replace('.', '_')}_wayback.jsonl"


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(6),
    wait=wait_exponential(min=10, max=120),
)
def get(endpoint, params=None):
    response = requests.get(endpoint, params=params, timeout=120)
    response.raise_for_status()
    return response


def earliest_capture(host, page):
    rows = get(
        CDX,
        {
            "url": f"{host}/{page}",
            "output": "json",
            "fl": "timestamp,original,statuscode,digest",
            "filter": "statuscode:200",
        },
    ).json()
    if len(rows) < 2:
        raise SystemExit(f"no successful capture of {page}")
    return dict(zip(rows[0], min(rows[1:]), strict=True))


def collect(host, pages):
    log = receipts(host)
    done = set()
    if log.exists():
        done = {
            json.loads(line)["path"]
            for line in log.read_text(encoding="utf-8").splitlines()
        }
    log.parent.mkdir(parents=True, exist_ok=True)
    for page in pages:
        target = folder(host) / urllib.parse.unquote(page)
        path = target.relative_to(ROOT).as_posix()
        if path in done:
            continue
        capture = earliest_capture(host, page)
        url = (
            f"https://web.archive.org/web/{capture['timestamp']}id_/"
            f"{capture['original']}"
        )
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
        with log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt, ensure_ascii=False) + "\n")
        print(f"{path}: {receipt['bytes']:,} bytes, captured {capture['timestamp']}")


def main():
    for host, pages in SITES.items():
        collect(host, pages)
    return 0


if __name__ == "__main__":
    sys.exit(main())

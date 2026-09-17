"""Download and read the SEC's 2016 seat-reservation roster PDFs.

The archive page lists, per district, PDFs for zila parishad members, samiti heads,
samiti members, mukhiyas and sarpanches. The PDFs carry text in the legacy
KrutiDev font encoding; only seat numbers (plain digits) and a small fixed
vocabulary of reservation labels are needed, so labels are looked up in a table
of their KrutiDev spellings and anything unrecognised stops the parse.
"""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from bs4 import BeautifulSoup
from sec_2016 import AGENT

DISTRICTS = 38
PAGE = "https://sec.bihar.gov.in/old-sec/Reservation.aspx"
BASE = "https://sec.bihar.gov.in/old-sec/"
# KrutiDev spellings of the roster's reservation labels, with their Unicode text.
# The typists' misspellings that occur are listed; nothing is matched loosely.
CATEGORY = {
    "vukjf{kr": "अनारक्षित",
    "vukfj{kr": "अनारक्षित",
    "vuqlwfpr tkfr": "अनुसूचित जाति",
    "vuqlqfpr tkfr": "अनुसूचित जाति",
    "vuwlwfpr tkfr": "अनुसूचित जाति",
    "vuqlkwfpr tkfr": "अनुसूचित जाति",
    "vuqlwfpr tutkfr": "अनुसूचित जनजाति",
    "vuqlwfpr tu tkfr": "अनुसूचित जनजाति",
    "vuqqlwfpr tutkfr": "अनुसूचित जनजाति",
    "fiNM+k oxZ": "पिछड़ा वर्ग",
    "fiN+M+k oxZ": "पिछड़ा वर्ग",
}
# Share of seat lines that may stay unread (one-off typing slips) before the parse
# is treated as broken; every unread line is reported.
MAX_UNREAD = 0.005
WOMEN = {"efgyk": "महिला", "vU;": "अन्य"}
# Districts typed the seat column differently ("la[;k & 9", "la[;k*&14", "{ks0&9",
# "la[;k 16"); common to all is a serial, a seat name, the seat number, an optional
# 2006 reservation code ("W", "SC W"), then the two reservation columns.
ROW = re.compile(
    r"^\s*(\d+)\s+(.*?\D)(\d+)\s+(?:([A-Za-z]{1,3}(?:\s?[Ww])?)\s+)?"
    r"("
    + "|".join(map(re.escape, CATEGORY))
    + r")\s+("
    + "|".join(map(re.escape, WOMEN))
    # A stray letter from the next column sometimes trails the row.
    + r")(?:\s+\S)?\s*$"
)


def download(raw):
    session = requests.Session()
    session.headers["User-Agent"] = AGENT
    soup = BeautifulSoup(session.get(PAGE, timeout=120).text, "html.parser")
    hidden = {
        i["name"]: i.get("value", "") for i in soup.select("input[type=hidden][name]")
    }
    buttons = [(i["name"], i["value"]) for i in soup.select("input[type=submit][name]")]
    if len(buttons) != DISTRICTS:
        raise ValueError(f"Expected {DISTRICTS} district buttons, found {len(buttons)}")
    folder = raw / "2016/reservation"
    folder.mkdir(parents=True, exist_ok=True)
    listing = []
    for name, label in buttons:
        page = BeautifulSoup(
            session.post(PAGE, data={**hidden, name: label}, timeout=120).text,
            "html.parser",
        )
        for link in page.select("a[href$='.pdf']"):
            href = link["href"]
            path = folder / href.replace("/", "__")
            status = 200
            if not path.exists():
                response = session.get(BASE + href, timeout=300)
                status = response.status_code
                if status == 200:
                    if not response.content.startswith(b"%PDF"):
                        raise ValueError(f"Not a PDF: {href}")
                    path.write_bytes(response.content)
            # Some linked PDFs no longer exist on the server; record, do not guess.
            listing.append(
                {
                    "district_button": label,
                    "href": href,
                    "status": status,
                    "file": path.name if path.exists() else None,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.exists()
                    else None,
                }
            )
    if not listing:
        raise ValueError("The archive page listed no roster PDFs")
    (folder / "listing.json").write_text(
        json.dumps(listing, indent=1, ensure_ascii=False)
    )
    missing = [x["href"] for x in listing if x["file"] is None]
    print(
        json.dumps(
            {"districts": len(buttons), "pdfs": len(listing), "missing": missing}
        )
    )


def parse(raw, out):
    folder = raw / "2016/reservation"
    rows, unread = [], []
    listing = json.loads((folder / "listing.json").read_text())
    if not listing:
        raise ValueError("Empty roster listing; run the download stage")
    for item in listing:
        if item["file"] is None:
            continue
        text = subprocess.run(
            ["pdftotext", "-layout", str(folder / item["file"]), "-"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        block = None
        for line in text.splitlines():
            if "iz[kaM" in line:
                block = line.split("iz[kaM", 1)[1].split(" ds ")[0].strip(" &-")
            match = ROW.match(line)
            if match:
                rows.append(
                    {
                        "file": item["file"],
                        "district_button": item["district_button"],
                        "office": item["href"].rsplit("/", 1)[-1].removesuffix(".pdf"),
                        "block_krutidev": block,
                        "serial": int(match.group(1)),
                        "seat_no": int(match.group(3)),
                        "reservation_2006": match.group(4),
                        "category": CATEGORY[match.group(5)],
                        "women": WOMEN[match.group(6)],
                        "source_line": line,
                    }
                )
            elif (
                re.match(r"^\s*\d+\s+\S", line)
                and "2006" not in line
                and any(word in line for word in (*CATEGORY, *WOMEN))
            ):
                unread.append({"file": item["file"], "line": line})
    pq.write_table(pa.Table.from_pylist(rows), out)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "unread_seat_lines": len(unread),
                "unread": unread,
            },
            ensure_ascii=False,
        )
    )
    if len(unread) > MAX_UNREAD * len(rows):
        raise ValueError("Too many roster lines with a seat number were not read")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["download", "parse"])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/statewide_2016"))
    parser.add_argument(
        "--out", type=Path, default=Path("data/interim/2016/reservation_roster.parquet")
    )
    args = parser.parse_args()
    if args.stage == "download":
        download(args.raw)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        parse(args.raw, args.out)


if __name__ == "__main__":
    main()

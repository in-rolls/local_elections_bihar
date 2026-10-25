"""The SEC's 2001 elected-mukhiya lists -> data/release/2001/mukhiya_winners.parquet

    python -m local_elections_bihar.parse.mukhiya_2001

Eight division PDFs saved from sec.bih.nic.in (collect/sec_wayback.py), set
in Akruti Dev (read with legacy_devanagari.akruti). Koshi's file also carries
Bhagalpur division, so all nine divisions are here. Each page has two columns
of block sections (block heading, then serial, panchayat, mukhiya); a district
heading runs across the page, so rows take the district of the last heading
above them, left column before right.

2001 had no reservation of mukhiya seats, so the table has none. The honorific
is kept as printed; '' is a ditto mark for the honorific of the row above.
"""

import argparse
import itertools
import re
import sys

import pdfplumber
from legacy_devanagari import akruti

from local_elections_bihar.parse.schema_2001 import TABLES
from local_elections_bihar.paths import RELEASE, ROOT, SEC_SITE
from local_elections_bihar.shared import release

SOURCES = sorted((SEC_SITE / "mukhiya").glob("*-Mukhiya.pdf"))
OUT = RELEASE / "2001"
CODE = ["parse/mukhiya_2001.py", "parse/schema_2001.py"]

SAME_LINE = 3  # points; chars of one printed line share a baseline to this
GAP = 9  # points; a wider forward jump starts a new cell
BACK = 15  # points; a backward jump this large starts a new run
SERIAL = re.compile(r"^\s*(\d+)\s*\.\s*(.*)$")
DITTO = re.compile(r"^\s*(?:''|\"|”|’’)\s*")
HONORIFICS = ("श्रीमती", "श्री", "सुश्री", "कुमारी", "मो0", "डा0", "डॉ0")


def cells(page):
    """Runs of characters in the order the PDF stores them, split at jumps."""
    out, cur = [], None
    for char in page.chars:
        if (
            cur
            and abs(char["top"] - cur["top"]) < SAME_LINE
            and -BACK < char["x0"] - cur["x1"] < GAP
        ):
            cur["text"] += char["text"]
            cur["x1"] = max(cur["x1"], char["x1"])
        else:
            cur = {k: char[k] for k in ("text", "x0", "x1", "top")}
            out.append(cur)
    return out


HEADINGS = {
    "division": re.compile(r"^प्रमंडल\s*[-:–]?\s*(.*)$"),
    "district": re.compile(r"^जिला\s*[-:–]?\s*(.*)$"),
    "block": re.compile(r"^प्रख(?:ं|ण्)?ड\s*[-:–]?\s*(.*)$"),
}


def heading(text, kind):
    """The name a heading cell gives, or None if the cell is not that heading."""
    match = HEADINGS[kind].match(akruti.to_unicode(text))
    return match.group(1).strip(" -:–") if match else None


def column_edge(found, width):
    """x where the right column starts: the widest gap between serial cells'
    x positions, or the page's middle when the page has one column."""
    starts = sorted({round(c["x0"]) for c in found if SERIAL.match(c["text"])})
    gaps = [(b - a, b) for a, b in itertools.pairwise(starts)]
    widest = max(gaps, default=(0, width / 2))
    return widest[1] - 5 if widest[0] > 100 else width / 2


def ordered(page):
    """Cells in reading order: district bands, then column, then line."""
    found = cells(page)
    middle = column_edge(found, page.width)
    bands = sorted(
        c["top"] for c in found if heading(c["text"], "district") is not None
    )
    for cell in found:
        cell["band"] = sum(top <= cell["top"] + SAME_LINE for top in bands)
        cell["column"] = int(cell["x0"] >= middle)
        cell["page_heading"] = any(
            heading(cell["text"], kind) is not None for kind in ("division", "district")
        )
    return sorted(
        found,
        key=lambda c: (
            c["band"],
            not c["page_heading"],
            c["column"],
            c["top"],
            c["x0"],
        ),
    )


def split_honorific(name):
    for word in HONORIFICS:
        if name == word or name.startswith(word + " "):
            return word, name[len(word) :].strip()
    return None, name


def rows(path):
    with pdfplumber.open(path) as pdf:
        return _rows(path, pdf)


def _rows(path, pdf):
    division = district = block = None
    honorific = None
    out = []
    for number, page in enumerate(pdf.pages, start=1):
        found = ordered(page)
        for cell in found:
            text = cell["text"]
            if "Commission" in text:
                continue
            if (name := heading(text, "division")) is not None:
                division = name or division
                continue
            if (name := heading(text, "district")) is not None:
                if not name:  # the name printed as its own cell, beside or below
                    near = [
                        c
                        for c in found
                        if c is not cell
                        and -SAME_LINE < c["top"] - cell["top"] < 25
                        and not c["page_heading"]
                        and not SERIAL.match(c["text"])
                    ]
                    near.sort(key=lambda c: (c["top"], c["x0"]))
                    name = akruti.to_unicode(near[0]["text"]) if near else None
                district = name
                block = None
                continue
            if (name := heading(text, "block")) is not None:
                block = name
                honorific = None
                continue
            match = SERIAL.match(text)
            if not match:
                continue
            line = sorted(
                (
                    c
                    for c in found
                    if c is not cell
                    and c["column"] == cell["column"]
                    and abs(c["top"] - cell["top"]) < SAME_LINE
                    and c["x0"] > cell["x1"]
                ),
                key=lambda c: c["x0"],
            )
            place = match.group(2)
            if not place.strip() and line:  # the name in its own cell
                place = line.pop(0)["text"]
            raw = " ".join(c["text"] for c in line)
            if not raw:  # the winner printed too close to the panchayat to split
                for mark in ("''", "Þeer"):
                    at = place.find(mark, 1)  # a name may begin with श्री
                    if at > 0:
                        place, raw = place[:at], place[at:]
                        break
            ditto = bool(DITTO.match(raw))
            title, name = split_honorific(akruti.to_unicode(DITTO.sub("", raw)))
            if title:
                honorific = title
            elif ditto:
                title = honorific
            out.append(
                {
                    "year": 2001,
                    "division": division,
                    "district": district,
                    "block": block,
                    "serial": int(match.group(1)),
                    "gram_panchayat": akruti.to_unicode(place),
                    "winner": name or None,
                    "winner_honorific": title,
                    "honorific_from_ditto": ditto and title is not None,
                    "winner_raw": raw.strip() or None,
                    "gram_panchayat_raw": place.strip(),
                    "source_path": path.relative_to(ROOT).as_posix(),
                    "source_page": number,
                }
            )
    return out


def build():
    table = [row for path in SOURCES for row in rows(path)]
    for row in table:
        if row["winner"] is None:  # a ditto mark with no name beside it
            row["winner_honorific"] = None
            row["honorific_from_ditto"] = False
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    if not parser.parse_args().check:
        release.write(
            OUT,
            {"mukhiya_winners": build()},
            TABLES,
            CODE,
            year=2001,
            source="sec.bih.nic.in division lists, via the Wayback Machine "
            "(data/raw/sec_bih_nic_in/mukhiya/)",
        )
    release.verify(OUT, TABLES)
    return 0


if __name__ == "__main__":
    sys.exit(main())

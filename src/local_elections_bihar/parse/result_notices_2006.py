"""2006 result notices (प्रपत्र-23, rule 83) from district collectorate sites.

Read by parse/release_2006.py.

The notice is the returning officer's publication of who was elected, one per
block (and one for the zila parishad), set in Kruti Dev. Each row is a seat:
serial, winner, post, the seat's caste reservation (आरक्षित/अनारक्षित), whether
it is reserved for a woman (महिला/अन्य), and the panchayat (ग्रा0 पं0 / ग्रा0 क0)
with its territorial constituency number. Unlike the SEC's mukhiya workbooks,
it states the mukhiya's and sarpanch's reservation. Madhubani's notices survive
(data/raw/madhubani_bih_nic_in/PanchayatElection2006/).

source_row is the row's line on the page (after empty lines are dropped):
some pages set the printed serial on a line of its own.

A row is read from its right end, where the fields come from closed lists:
महिला/अन्य, then the caste, then the post; what is left is the name. A row
that wraps (a name's "(निर्विरोध)" on the next line) is joined first.
"""

import re
import subprocess

from local_elections_bihar.parse.members_2006 import reserved_caste, reserved_woman
from local_elections_bihar.parse.sec_workbooks import relative
from local_elections_bihar.paths import RAW
from local_elections_bihar.year2011.hindi import kruti_text

SOURCES = {"मधुबनी": RAW / "madhubani_bih_nic_in" / "PanchayatElection2006"}
OFFICE = {
    ("gram_panchayat", "मुखिया"): "mukhiya",
    ("gram_panchayat", "सदस्य"): "ward_member",
    ("gram_kachahari", "सरपंच"): "sarpanch",
    ("gram_kachahari", "पंच"): "panch",
    ("panchayat_samiti", "सदस्य"): "panchayat_samiti_member",
    ("zila_parishad", "सदस्य"): "zila_parishad_member",
}
CASTE = (
    r"(?:अनारक्षित|सामान्य|पिछड़ा(?:\s*वर्ग)?|अनु0\s*जाति|अनु0\s*ज0\s*जा0"
    r"|अनुसूचित\s*जन\s*जाति|अनुसूचित\s*जाति)"
)
# The name is greedy: a winner can be called मुखिया ("बिल्टू मुखिया"), so the
# post is the last post word that leaves a well-formed rest.
ROW = re.compile(
    rf"^(?:(?P<serial>\d+)\s+)?(?P<name>.+)\s+(?P<post>मुखिया|सदस्य|सरपंच|पंच)"
    rf"(?:\s+(?P<caste>{CASTE}))?\s+(?P<woman>महिला|अन्य)\s+(?P<place>.+)$"
)
# ग्रा0 पं0 (gram panchayat) or ग्रा0 क0 / कचहरी (gram kachahari), typed
# variously: गा्र0, गा0, ग्र0. The constituency part can be missing.
PANCHAYAT = re.compile(
    r"(?:ग्रा|गा्र|गा|ग्र)0\s*(?P<body>पं0|क0|कचहरी|पंचायत)\s*"
    r"(?P<name>.+?)\s*(?:,?\s*प्रा?0\s*नि0.*)?$"
)
CONSTITUENCY = re.compile(r"(?:क्षे0\s*सं0|क्षे=?|क्षेत्र)\s*[-–]?\s*0*(\d+)")
BLOCK = re.compile(r"प्रख(?:ण्|ं)ड\s*[-–]\s*(\S+)")
COLUMN_NUMBERS = re.compile(r"^1( \d)+$")


def decode(line):
    text = " ".join(line.split())
    try:
        return kruti_text(text)
    except ValueError:
        return None


def pages(path):
    text = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return text.split("\f")


def rows():
    out = []
    for district, folder in SOURCES.items():
        for path in sorted(folder.glob("*.pdf")):
            zila = "Zila" in path.name
            block = None
            for number, page in enumerate(pages(path), start=1):
                lines = [decode(line) for line in page.splitlines() if line.strip()]
                lines = [line for line in lines if line]
                for line in lines[:12]:
                    if found := BLOCK.search(line):
                        block = found[1].strip(" ,")
                # A row starts at a serial or, where the serial sits on its own
                # line, at a line that is already a whole row.
                joined = []
                for index, line in enumerate(lines):
                    starts = re.match(r"^\d+\s", line) or ROW.match(line)
                    if starts and not COLUMN_NUMBERS.match(line):
                        joined.append((index, line))
                    elif joined and not ROW.match(joined[-1][1]):
                        joined[-1] = (joined[-1][0], f"{joined[-1][1]} {line}")
                for index, line in joined:
                    match = ROW.match(line)
                    if not match:
                        continue
                    place = match["place"]
                    panchayat = PANCHAYAT.search(place)
                    # The heading sentence is boilerplate copied between
                    # tables; the place column says which body the seat is in.
                    if zila:
                        body = "zila_parishad"
                    elif panchayat:
                        kachahari = panchayat["body"] in {"क0", "कचहरी"}
                        body = "gram_kachahari" if kachahari else "gram_panchayat"
                    else:
                        body = "panchayat_samiti"
                    office = OFFICE.get((body, match["post"]))
                    if office is None:
                        continue
                    seat = CONSTITUENCY.search(place)
                    name = match["name"].strip()
                    unopposed = "निर्विरोध" in name
                    caste_local = match["caste"]
                    out.append(
                        {
                            "office": office,
                            "district": district,
                            "district_from_file": district,
                            "block": None if zila else block,
                            "gram_panchayat": panchayat["name"].strip()
                            if panchayat
                            and office
                            in {"ward_member", "panch", "mukhiya", "sarpanch"}
                            else None,
                            "constituency_no": int(seat[1]) if seat else None,
                            "constituency_name": place,
                            "winner": re.sub(r"\s*\(?निर्विरोध\)?\s*", " ", name).strip()
                            or None,
                            "winner_raw": None,
                            "vacant": False,
                            "unopposed": unopposed,
                            "source_document": "result_notice",
                            "reserved_raw": " / ".join(
                                t for t in (caste_local, match["woman"]) if t
                            ),
                            "reserved_caste_local": caste_local,
                            "reserved_caste": reserved_caste(caste_local),
                            "reserved_woman_raw": match["woman"],
                            "reserved_woman": reserved_woman(match["woman"]),
                            "source_path": relative(path),
                            "source_sheet": f"page {number}",
                            "source_row": index + 1,
                        }
                    )
    # A row printed twice (same seat, winner and reservation) is one seat.
    seen, unique = set(), []
    for row in out:
        key = (
            row["office"],
            row["block"],
            row["gram_panchayat"],
            row["constituency_no"],
            row["winner"],
            row["reserved_raw"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique

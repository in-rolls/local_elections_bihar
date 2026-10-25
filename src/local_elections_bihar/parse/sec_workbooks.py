"""Read the SEC's 2006 Kruti Dev workbooks cell by cell.

The workbooks under data/raw/sec_documents/ (Mukhiya_2006/, Sarpanch/,
GPS_GKP_PSS_ZPS/) are typed in Kruti Dev 010, a font that draws Devanagari over
Latin bytes. Each cell is decoded with year2011.hindi.kruti_text. A cell the
decoder refuses keeps its bytes in the row's raw column and reads as null
rather than as a guess.

Headings sit in the data rows: "जिला - गया", "प्रखंड - बोधगया",
"पंचायत - नावाँ" in the member workbooks; "जिला का नाम:" and "प्रखण्ड का नाम:"
followed by the value in the next cell in the profile workbooks. A heading
holds until the next one.
"""

import re
from dataclasses import dataclass, field

import xlrd

from local_elections_bihar.paths import ROOT
from local_elections_bihar.year2011.hindi import kruti_text

HEADINGS = {
    "district": re.compile(r"^जिला(?:\s*का\s*नाम\s*[-–:]?|\s*[-–:])\s*(.*)$"),
    "block": re.compile(r"^प्रख(?:ं|ण्)ड(?:\s*का\s*नाम\s*[-–:]?|\s*[-–:])\s*(.*)$"),
    # A gram kachahari covers the same area as its gram panchayat and is
    # headed by the same name ("ग्राम कचहरी - नावाँ").
    "gram_panchayat": re.compile(
        r"^(?:ग्राम\s*)?(?:पंचायत|कचहरी)(?:\s*का\s*नाम)?\s*[-–:]\s*(.*)$"
    ),
}


def decode(value):
    """(decoded text or None, raw text) for one cell."""
    if isinstance(value, float):
        value = str(int(value)) if value.is_integer() else str(value)
    if not isinstance(value, str) or not value.strip():
        return None, None
    try:
        text = kruti_text(value)
    except ValueError:
        return None, value
    return " ".join(text.split()) or None, value


@dataclass
class Context:
    district: str | None = None
    block: str | None = None
    gram_panchayat: str | None = None
    seen: dict = field(default_factory=dict)

    def update(self, cells):
        """Apply any heading in this row; True if the row was a heading."""
        found = False
        for i, text in enumerate(cells):
            if not text:
                continue
            for level, pattern in HEADINGS.items():
                match = pattern.match(text)
                if not match:
                    continue
                value = match[1].strip()
                if not value:  # "जिला का नाम:" with the value in a later cell
                    value = next((c for c in cells[i + 1 :] if c), "")
                setattr(self, level, value or None)
                if level == "district":
                    self.block = self.gram_panchayat = None
                elif level == "block":
                    self.gram_panchayat = None
                found = True
                break
        return found


def sheets(path):
    """(sheet name, list of rows of (decoded, raw) cells) for every sheet."""
    book = xlrd.open_workbook(path)
    for sheet in book.sheets():
        rows = [
            [decode(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
            for r in range(sheet.nrows)
        ]
        yield sheet.name, rows


def relative(path):
    return path.relative_to(ROOT).as_posix()

"""2006 mukhiya and sarpanch winners, from the SEC's profile workbooks.

Read by parse/release_2006.py.

data/raw/sec_documents/Mukhiya_2006/<district>.xls (38 districts) and
Sarpanch/<district>.xls (35) list, block by block, each gram panchayat's
elected head with the profile the SEC collected: age, education, social
standing (उच्च/मध्यम/निम्न वर्ग), the winner's own caste category, annual
income, occupation, and number of sons and daughters. They state no seat
reservation and no sex.

A row is one gram panchayat: rows with a serial number. Samastipur's mukhiya
workbook repeats one filler row ("उ", "उमा देवी") about 20,000 times below its
352 numbered rows; those rows carry no serial and are not read.

The address and telephone column is left out of the release: it identifies
private people and the raw workbook keeps it.
"""

import re

from local_elections_bihar.parse.sec_workbooks import Context, relative, sheets
from local_elections_bihar.paths import SEC_DOCUMENTS

SOURCES = {
    "mukhiya": SEC_DOCUMENTS / "Mukhiya_2006",
    "sarpanch": SEC_DOCUMENTS / "Sarpanch",
}
SERIAL = re.compile(r"^\d+$")
DIGITS = re.compile(r"^\d[\d,]*$")


def winner_caste(text):
    """The winner's own category as printed, in the state's enum, or None."""
    if not text:
        return None
    if re.search(r"ज0\s*जा|जनजा|जन\s*जा", text):
        return "ST"
    if re.search(r"अनु|अ0\s*जा|अनुसू", text):
        return "SC"
    if re.search(r"अत्य|अति|^अ0\s*पि", text) and "पि" in text:
        return "EBC"
    if "पि" in text:
        return "BC"
    if re.search(r"सामान्य|अनारक्षित|सवर्ण", text):
        return "NONE"
    return None


def number(text):
    return int(text.replace(",", "")) if text and DIGITS.match(text) else None


def age(text):
    """A printed 0 means the age was not given."""
    value = number(text)
    return value or None


def rows(office, folder):
    out = []
    for path in sorted(folder.glob("*.xls")):
        workbook = list(sheets(path))
        # Continuation sheets (Sheet2) carry a block heading but no district;
        # the workbook is one district.
        heading = Context()
        for _, cells in workbook:
            for row in cells:
                if heading.update([c[0] for c in row]) and heading.district:
                    break
            if heading.district:
                break
        for sheet, cells in workbook:
            context = Context(district=heading.district)
            last_serial, headed = 0, False
            for index, row in enumerate(cells):
                text = [c[0] for c in row]
                if context.update(text):
                    headed = True
                    continue
                if not text or not SERIAL.match(text[0] or ""):
                    continue
                # Some workbooks head only their first block. Numbering that
                # starts again with no heading is a new block whose name is
                # not printed, not more of the last one.
                if int(text[0]) <= last_serial and not headed:
                    context.block = None
                last_serial, headed = int(text[0]), False
                text += [None] * (12 - len(text))
                if text[1] is None and text[2] is None:
                    continue  # a numbered template line: no panchayat, no winner
                out.append(
                    {
                        "office": office,
                        "district": context.district or heading.district,
                        "district_from_file": path.stem.strip(),
                        "block": context.block,
                        "serial": int(text[0]),
                        "gram_panchayat": text[1],
                        "winner": text[2],
                        "winner_raw": row[2][1] if len(row) > 2 else None,
                        "winner_age": age(text[3]),
                        "winner_education_raw": text[5],
                        "winner_social_class_raw": text[6],
                        "winner_caste_raw": text[7],
                        "winner_caste": winner_caste(text[7]),
                        "winner_income_inr": number(text[8]),
                        "winner_income_raw": text[8],
                        "winner_occupation_raw": text[9],
                        "winner_sons": number(text[10]),
                        "winner_daughters": number(text[11]),
                        "source_path": relative(path),
                        "source_sheet": sheet,
                        "source_row": index + 1,
                    }
                )
    return out

"""2006 member seats with their reservation, from the SEC's district workbooks.

Read by parse/release_2006.py.

data/raw/sec_documents/GPS_GKP_PSS_ZPS/<division>/<district>_*.xls has one
sheet per office: GPS gram panchayat ward member, GKP gram kachahari panch,
PSS panchayat samiti member, ZPS zila parishad member. A row is one seat:
constituency number and name, winner, the seat's caste reservation
(आरक्षित/अनारक्षित) and whether it is reserved for a woman (महिला/अन्य).
32 of Bihar's 38 districts are present.

The caste cell is typed freely (177 spellings: "अनु0 जाति", "अ0 ज0 जा0",
"पि0 वर्ग", "अनारिक्षत" ...). It is read by the ordered rules in
`reserved_caste`; a cell naming two categories, or too little to tell, reads
null. release_2006 writes data/checks/reserved_2006_vocabulary.csv, listing
every spelling with its reading and count. A seat whose winner is "----" or
"रिक्त" (vacant) has no winner but keeps its reservation.
"""

import re

from local_elections_bihar.parse.sec_workbooks import Context, relative, sheets
from local_elections_bihar.paths import SEC_DOCUMENTS

SOURCE = SEC_DOCUMENTS / "GPS_GKP_PSS_ZPS"
OFFICES = {
    "GPS": "ward_member",
    "GKP": "panch",
    "PSS": "panchayat_samiti_member",
    "ZPS": "zila_parishad_member",
}
SEAT = re.compile(r"^0*(\d+)\s*[-–.]?\s*(.*)$")
EMPTY = re.compile(r"^[-–\s]*$")
VACANT = {"रिक्त"}
# The seat's own category, then the forms that only say "reserved".
RESERVED_WORD = re.compile(r"आरक्षित|आर0|आ0|[;()]|द्ध")
ST = re.compile(r"ज0|जन\s*0?\s*जा|जनजा")
SC = re.compile(r"(?:अनु|अ0|अन0|अनुसू?ु?च|अनूु|अुनु|अनुु).*जा|^अ0\s*जा")
BC = re.compile(r"पि|पछ")
OPEN = re.compile(r"^(?:अना|अनार|सामान्य)")


def reserved_caste(text):
    """The seat's category from its printed caste cell, or None."""
    if not text or EMPTY.match(text) or text in VACANT:
        return None
    if re.search(r"अना|सामान्य", text) and re.search(r"जा|पि|ज0", text):
        return None  # names two categories
    core = RESERVED_WORD.sub(" ", text).strip()
    if OPEN.match(core):
        return "NONE"
    if ST.search(core):
        return "ST"
    if SC.search(core):
        return "SC"
    if BC.search(core):
        return "BC"
    return None


def reserved_woman(text):
    if not text:
        return None
    if "महि" in text or "मलि" in text:
        return 1
    if text in {"अन्य", "अनय", "पुरूष"}:
        return 0
    return None


def rows():
    out = []
    for path in sorted(SOURCE.glob("*/*.xls")):
        district_from_file = path.name.split("_")[0].strip()
        workbook = list(sheets(path))
        # Some ZPS sheets carry no district heading; the workbook is one district.
        heading = Context()
        for _, cells in workbook:
            for row in cells:
                heading.update([c[0] for c in row])
                if heading.district:
                    break
            if heading.district:
                break
        for sheet, cells in workbook:
            office = OFFICES.get(sheet)
            if office is None:
                continue
            context = Context()
            for index, row in enumerate(cells):
                text = [c[0] for c in row]
                if context.update(text):
                    continue
                seat = SEAT.match(text[0] or "") if text else None
                if not seat or len(text) < 4:
                    continue
                winner = text[1]
                vacant = winner is None or bool(EMPTY.match(winner)) or winner in VACANT
                caste_local, woman_local = text[2], text[3]
                out.append(
                    {
                        "office": office,
                        "district": context.district or heading.district,
                        "district_from_file": district_from_file,
                        "block": context.block,
                        "gram_panchayat": (
                            context.gram_panchayat
                            if office in {"ward_member", "panch"}
                            else None
                        ),
                        "constituency_no": int(seat[1]),
                        "constituency_name": seat[2].strip() or None,
                        "winner": None if vacant else winner,
                        "winner_raw": row[1][1],
                        "vacant": vacant,
                        "reserved_raw": " / ".join(
                            t for t in (caste_local, woman_local) if t
                        )
                        or None,
                        "reserved_caste_local": caste_local,
                        "reserved_caste": reserved_caste(caste_local),
                        "reserved_woman_raw": woman_local,
                        "reserved_woman": reserved_woman(woman_local),
                        "source_path": relative(path),
                        "source_sheet": sheet,
                        "source_row": index + 1,
                    }
                )
    return out

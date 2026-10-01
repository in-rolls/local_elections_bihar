"""Decode the reviewed embedded fonts in the 2011 Gaya pilot PDFs."""

import hashlib
import io
import json
import re
import unicodedata
from pathlib import Path

import pdfplumber
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

MAP = Path(__file__).with_name("font_map_2011.json")
CONSONANTS = "क-हक़-य़"
CLUSTER = rf"[{CONSONANTS}]़?(?:्[{CONSONANTS}]़?)*"


def logical_text(text):
    """Undo visual-order short-i and reph glyphs; preserve source spelling."""
    text = re.sub(
        rf"ि([ंँ]?)(\ue000?)({CLUSTER})",
        lambda m: ("र्" if m[2] else "") + m[3] + "ि" + m[1],
        text,
    )
    text = re.sub(rf"({CLUSTER}[ािीुूृॄेैोौंँ़]*)\ue000", r"र्\1", text)
    if "\ue000" in text:
        raise ValueError(f"Unresolved reph: {text!r}")
    return unicodedata.normalize("NFC", " ".join(text.split()))


def decoded_pdf(path):
    """Repair ToUnicode in memory; the original PDF is never modified."""
    maps = json.loads(MAP.read_text())["fonts"]
    reader = PdfReader(path)
    patched = set()
    for page in reader.pages:
        for reference in page["/Resources"]["/Font"].values():
            font = reference.get_object()
            if id(font) in patched:
                continue
            patched.add(id(font))
            original = font.get("/ToUnicode")
            if original is None or b"<09" not in original.get_data():
                continue
            binary = font["/FontDescriptor"]["/FontFile2"].get_data()
            digest = hashlib.sha256(binary).hexdigest()
            if digest not in maps:
                raise ValueError(f"Unreviewed Hindi font {digest} in {path}")
            characters = maps[digest]["characters"]
            lines = [
                "/CIDInit /ProcSet findresource begin 12 dict begin begincmap",
                "1 begincodespacerange <00> <ff> endcodespacerange",
                f"{len(characters)} beginbfchar",
                *[
                    f"<{int(code):02x}> <{value.encode('utf-16-be').hex()}>"
                    for code, value in characters.items()
                ],
                "endbfchar endcmap end end",
            ]
            stream = DecodedStreamObject()
            stream.set_data("\n".join(lines).encode())
            font[NameObject("/ToUnicode")] = stream
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    buffer = io.BytesIO()
    writer.write(buffer)
    return pdfplumber.open(buffer)


def cell_text(page, box):
    """Keep PDF drawing order inside a cell; x-sorting scrambles Hindi marks."""
    if box is None:
        return None
    chars = [
        char
        for char in page.chars
        if box[0] <= (char["x0"] + char["x1"]) / 2 < box[2]
        and box[1] <= (char["top"] + char["bottom"]) / 2 < box[3]
    ]
    return logical_text("".join(char["text"] for char in chars))


def kruti_text(text):
    """Decode Kruti Dev 010 using the attributed mapping and shared mark ordering."""
    pairs = json.loads(Path(__file__).with_name("kruti_dev_010.json").read_text())[
        "mapping"
    ]
    for old, new in pairs:
        text = text.replace(old, new)
    text = (
        text.replace("±", "Zं")
        .replace("Æ", "र्f")
        .replace("Ç", "fं")
        .replace("É", "र्fं")
        .replace("Ê", "ीZ")
        .replace("f", "ि")
        .replace("Z", "\ue000")
    )
    return logical_text(text)

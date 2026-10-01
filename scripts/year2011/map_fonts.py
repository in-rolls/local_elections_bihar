"""Reconstruct collection glyph maps from the SHA-pinned Arial Unicode font.

The reference font is proprietary and is not distributed. Ordinary parsing uses
the committed map and does not require that font or this derivation step.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont
from pypdf import PdfReader

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--font", type=Path, required=True)
parser.add_argument("--raw", type=Path, default=Path("data/2011/raw/reports"))
parser.add_argument("--out", type=Path, required=True)
parser.add_argument(
    "--glob",
    action="append",
    default=[],
    help="Additional source globs relative to --raw",
)
args = parser.parse_args()
fullpath = args.font
expected = "876af2cd4854644e7f3e7feb2f688997fdb3343c6df6693611209c9dfb47ccec"
if hashlib.sha256(fullpath.read_bytes()).hexdigest() != expected:
    raise ValueError("Reference font differs from the reviewed font")
full = TTFont(fullpath)


def key(f, n):
    co, ends, flags = f["glyf"][n].getCoordinates(f["glyf"])
    return hashlib.sha256(
        repr((list(co), list(ends), list(flags))).encode()
    ).hexdigest()


texts = {
    n: chr(c)
    for c, n in full.getBestCmap().items()
    if 0x900 <= c <= 0x97F or c == 0x25CC
}
texts.update(space=" ", glyph06981="\ue000", glyph06982="्र")
for _ in range(20):
    changes = 0
    for lookup in full["GSUB"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            for a, b in getattr(st, "mapping", {}).items():
                if isinstance(b, str) and a in texts and b not in texts:
                    texts[b] = texts[a]
                    changes += 1
            for a, ls in getattr(st, "ligatures", {}).items():
                for lig in ls:
                    seq = [a, *lig.Component]
                    if all(n in texts for n in seq) and lig.LigGlyph not in texts:
                        texts[lig.LigGlyph] = "".join(texts[n] for n in seq)
                        changes += 1
    if not changes:
        break
texts.update(
    glyph07410="िं",
    glyph07414="ि\ue000",
    glyph07411="िं",
    glyph07418="िं\ue000",
    glyph07416="ि\ue000",
)
rev = defaultdict(set)
for n, t in texts.items():
    rev[key(full, n)].add(t)
root = args.raw
files = [
    "winners/GAYA/GAYA_GPM.pdf",
    "runners/GAYA/GAYA_gpm.pdf",
]
files += sorted(
    {str(p.relative_to(root)) for pattern in args.glob for p in root.glob(pattern)}
    - set(files)
)
out = {
    "method": (
        "Exact glyph outline matches to reference font; GSUB decomposition; "
        "contextual i-matra/reph/nasal forms visually checked in a glyph sheet. "
        "U+E000 is a temporary reph marker, removed by decoder."
    ),
    "reference_font": {
        "name": "Arial Unicode",
        "sha256": hashlib.sha256(fullpath.read_bytes()).hexdigest(),
    },
    "fonts": {},
}
for file in files:
    for page in PdfReader(root / file).pages:
        for ref in page["/Resources"]["/Font"].values():
            font = ref.get_object()
            tu = font.get("/ToUnicode")
            if tu is None or b"<09" not in tu.get_data():
                continue
            data = font["/FontDescriptor"]["/FontFile2"].get_data()
            sha = hashlib.sha256(data).hexdigest()
            if sha in out["fonts"]:
                continue
            ft = TTFont(BytesIO(data))
            mapping = {}
            unmapped = []
            for code, n in ft["cmap"].tables[0].cmap.items():
                vals = rev.get(key(ft, n), set())
                if len(vals) == 1:
                    mapping[str(code - 0xF000)] = next(iter(vals))
                else:
                    unmapped.append((code - 0xF000, n, list(vals)))
            print(file, font["/BaseFont"], "mapped", len(mapping), "unmapped", unmapped)
            if unmapped:
                raise ValueError(f"Unmapped glyphs: {unmapped}")
            out["fonts"][sha] = {
                "first_source": file,
                "basefont": str(font["/BaseFont"]),
                "characters": mapping,
            }
args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")

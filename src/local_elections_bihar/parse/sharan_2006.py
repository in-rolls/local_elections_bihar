"""Read M. R. Sharan's 2006 gram panchayat head reservations (a Stata file).

One row per gram panchayat: English district, block and GP names and four 0/1
flags for the head (mukhiya) seat. The file is a research file whose label
credits the State Election Commission; how it was built is not documented
(data/raw/sharan/README.md), so nothing here is read as an SEC original.

The three caste flags never coincide, so they fold into one reserved_caste.
EBC is kept as the file names it: the notices and workbooks of 2006 print
पिछड़ा वर्ग, read BC elsewhere in this release, and the two are not equated.
"""

import re

from pandas.io.stata import StataReader

from local_elections_bihar.paths import ROOT, SHARAN

SOURCE = SHARAN / "Bihar_GP_Reservation_2006.dta"
FLAGS = {
    "sc_reserved_2006": "SC",
    "st_reserved_2006": "ST",
    "ebc_reserved_2006": "EBC",
}
WOMAN = "women_reserved_2006"
# What the file says its columns mean. A re-sent file that codes them
# differently must stop the build, not be read under the old meaning.
LABELS = {
    "UGP": "GP identifier (unique within this file)",
    "DistrictName": "District",
    "SubDistrictName": "Block",
    "GramPanchayatName": "Gram panchayat",
    "sc_reserved_2006": "GP head seat reserved for SC, 2006 (SEC)",
    "st_reserved_2006": "GP head seat reserved for ST, 2006 (SEC)",
    "ebc_reserved_2006": "GP head seat reserved for EBC (backward classes), 2006 (SEC)",
    "women_reserved_2006": "GP head seat reserved for women, 2006 (SEC)",
}
VALUES = {"yn": {0: "No", 1: "Yes"}}
# A no-break space saved as Latin-1 and re-encoded prints as "Â" + U+00A0.
MOJIBAKE = re.compile("\u00c2?\u00a0")


def clean(name):
    return " ".join(MOJIBAKE.sub(" ", name).split())


def frame(path=SOURCE):
    with StataReader(path, convert_categoricals=False) as reader:
        table = reader.read()
        labels = reader.variable_labels()
        values = {
            name: {int(k): v for k, v in codes.items()}
            for name, codes in reader.value_labels().items()
        }
    if labels != LABELS or values != VALUES:
        raise SystemExit(f"{path.name}: variable or value labels have changed")
    return table


def rows(path=SOURCE):
    table = frame(path)
    flags = table[[*FLAGS, WOMAN]]
    if not flags.isin([0, 1]).all(axis=None):
        raise SystemExit(f"{path.name}: a reservation flag is neither 0 nor 1")
    if (table[list(FLAGS)].sum(axis=1) > 1).any():
        raise SystemExit(f"{path.name}: a seat is reserved for two castes")
    relative = path.relative_to(ROOT).as_posix()
    out = []
    for number, row in enumerate(table.to_dict("records"), start=1):
        caste = next((c for flag, c in FLAGS.items() if row[flag] == 1), "NONE")
        out.append(
            {
                "ugp": int(row["UGP"]),
                "district": row["DistrictName"],
                "block": row["SubDistrictName"],
                "gram_panchayat": clean(row["GramPanchayatName"]),
                "gram_panchayat_raw": row["GramPanchayatName"],
                "reserved_caste": caste,
                "reserved_woman": int(row[WOMAN]),
                "source_path": relative,
                "source_row": number,
            }
        )
    return out

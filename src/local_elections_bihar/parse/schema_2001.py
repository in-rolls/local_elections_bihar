"""Release contract for the 2001 mukhiya winners."""

import pandera.polars as pa
import polars as pl

from local_elections_bihar.shared.schema import field, nullable


class MukhiyaWinner(pa.DataFrameModel):
    year: pl.Int16 = field("Election year, printed in each list's title.", isin=[2001])
    division: pl.Utf8 = field("Division heading (प्रमंडल), as printed.")
    district: pl.Utf8 = field("District heading (जिला), as printed.")
    block: pl.Utf8 = field("Block heading (प्रखंड), as printed.")
    serial: pl.Int32 = field("Serial printed within the block.")
    gram_panchayat: pl.Utf8 = field("Gram panchayat, decoded from Akruti.")
    winner: pl.Utf8 = nullable(
        "Elected mukhiya, decoded, honorific removed; null where the list prints "
        "no name."
    )
    winner_honorific: pl.Utf8 = nullable(
        "श्री, श्रीमती ... as printed, or carried from the row above when the list "
        "prints the ditto mark ''; null where no name is printed."
    )
    honorific_from_ditto: pl.Boolean = field(
        "winner_honorific came from the row above through a ditto mark."
    )
    winner_raw: pl.Utf8 = nullable("The winner cell's Akruti bytes.")
    gram_panchayat_raw: pl.Utf8 = field("The panchayat cell's Akruti bytes.")
    source_path: pl.Utf8 = field("Division list the row was read from.")
    source_page: pl.Int32 = field("One-based page in that list.")


TABLES = {"mukhiya_winners": MukhiyaWinner}

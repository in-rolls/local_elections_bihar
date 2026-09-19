"""Audit the 2016 panchayat release against sources that share no code with it.

Schema checks (types, domains, keys) live in schemas_2016 and run during the
build. This audit compares the release with the form's own seat frame, with the
six CSVs collected from the same form years earlier by other code, with the SEC's
reservation roster PDFs and with a fresh urllib re-request, and prints the
distributions that would expose a wrong parse.
"""

import argparse
import http.cookiejar
import json
import random
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq
from bs4 import BeautifulSoup

URL = "https://sec.bihar.gov.in/old-sec/ovc.aspx"
AGENT = "Mozilla/5.0 (compatible; local-elections-bihar research archive; audit)"
KEY = ["office", "district_code", "block_code", "panchayat_code", "unit_code"]
GEO = ["district", "block", "panchayat", "unit"]
# Legacy column holding the seat's dropdown label, by office.
LEGACY_UNIT = {
    "mukhiya": "panchayat",
    "sarpanch": "panchayat",
    "ward_member": "ward",
    "panch": "ward",
    "panchayat_samiti_member": "number",
    "zila_parishad_member": "number",
}
# Release column for each legacy candidate column.
LEGACY_FIELDS = {
    "sr_no": "sr_no",
    "candidate_name": "candidate_name",
    "father_husband_name": "father_husband_name",
    "gender": "gender_raw",
    "age": "age_raw",
    "category": "category",
    "educ": "education",
    "mobile_number": "mobile_number",
    "address": "address",
    "email": "email",
    "valid_vote": "votes_raw",
    "remarks": "remarks",
}
# Compared per seat, apart from the candidate rows: the form's reservation label
# is not stable. Kaimur zila parishad seat 9 read 'अनारक्षित(महिला)' when the legacy
# files were collected, reads 'अनारक्षित' now, and the roster PDF reserves it for women.
RESERVATION = {"reservation_status": "seat_reservation"}
OFFICE_CODES = {
    "zila_parishad_member": "0102",
    "panchayat_samiti_member": "0105",
    "mukhiya": "0107",
    "sarpanch": "0108",
    "ward_member": "0109",
    "panch": "0110",
}
LAST_FIELD = {
    "0102": "ddlPradesik",
    "0105": "ddlPradesik",
    "0107": "ddlPanchayat",
    "0108": "ddlPanchayat",
    "0109": "ddlWard",
    "0110": "ddlWard",
}
# Roster file names, lower-cased, to offices; samiti heads (pramukh) are not seats
# of the results form.
ROSTER_OFFICES = {
    "zila": "zila_parishad_member",
    "sadasya": "panchayat_samiti_member",
    "mukhi": "mukhiya",
    "sarpanch": "sarpanch",
}
ROSTER_DISTRICTS = {"KAIMUR": "KAIMUR (BHABUA)"}
WOMEN = "(महिला)"
SEAT_CATEGORY = {"अनुसूचित जाति", "अनुसूचित जनजाति"}
PAGE_SIZE = 20
RETRIES = 4


def clean(column):
    """Cell text as both collections can be compared: spacing and the form's
    '-' and '--' blanks are presentation, and the legacy files kept a serial's
    leading zero."""
    text = (
        pl.col(column)
        .cast(pl.Utf8)
        .fill_null("")
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
    )
    text = (
        pl.when(text.is_in(["-", "--", "--select--"])).then(pl.lit("")).otherwise(text)
    )
    if column == "sr_no":
        text = text.str.replace(r"^0+(\d)", "$1")
    return text.alias(column)


def release_rows(seats, candidates):
    labels = seats.unique(KEY, keep="first").select(
        *KEY, *GEO, "seat_reservation", "code_repeated"
    )
    rows = candidates.join(labels, on=KEY, how="left", nulls_equal=True)
    return rows.select(
        "office",
        "code_repeated",
        *GEO,
        *[
            pl.col(new).alias(old)
            for old, new in {**LEGACY_FIELDS, **RESERVATION}.items()
        ],
    )


def legacy_rows(folder, office):
    table = pl.read_parquet(folder / f"{office}.parquet")
    unit = LEGACY_UNIT[office]
    has_panchayat = unit == "ward"
    return table.select(
        pl.lit(office).alias("office"),
        "district",
        (pl.col("block") if "block" in table.columns else pl.lit(None, pl.Utf8)).alias(
            "block"
        ),
        (pl.col("panchayat") if has_panchayat else pl.lit(None, pl.Utf8)).alias(
            "panchayat"
        ),
        pl.col(unit).alias("unit"),
        *LEGACY_FIELDS,
        *RESERVATION,
    )


def compare_legacy(seats, candidates, folder, examples=20):
    """Row-for-row agreement with the legacy files, as sets of whole rows per seat.

    Only blocks present in the release are compared, so a partial release is
    judged on what it holds; legacy rows elsewhere are counted, not called missing.
    """
    seat = ["office", *GEO]
    columns = [*seat, *LEGACY_FIELDS]
    new = release_rows(seats, candidates)
    repeated = new.filter("code_repeated").select(seat).unique().height
    new = new.select(clean(c) for c in [*columns, *RESERVATION]).unique()
    report, flags = {"seats_with_reused_code": repeated, "offices": {}}, []
    for office in LEGACY_UNIT:
        old = legacy_rows(folder, office).select(
            clean(c) for c in [*columns, *RESERVATION]
        )
        mine = new.filter(pl.col("office") == office)
        labels = (
            mine.select(*seat, *RESERVATION)
            .unique()
            .join(old.select(*seat, *RESERVATION).unique(), on=seat, suffix="_legacy")
            .filter(pl.col("reservation_status") != pl.col("reservation_status_legacy"))
        )
        old, mine = old.select(columns).unique(), mine.select(columns).unique()
        blocks = mine.select("district", "block").unique()
        inside = old.join(blocks, on=["district", "block"], how="semi")
        only_old = inside.join(mine, on=columns, how="anti")
        only_new = mine.join(inside, on=columns, how="anti")
        old_seats, new_seats = inside.select(seat).unique(), mine.select(seat).unique()
        report["offices"][office] = {
            "legacy_rows": inside.height,
            "release_rows": mine.height,
            "identical_rows": inside.height - only_old.height,
            "legacy_only_rows": only_old.height,
            "release_only_rows": only_new.height,
            "legacy_rows_outside_release_blocks": old.height - inside.height,
            "seats_legacy_only": old_seats.join(new_seats, on=seat, how="anti").height,
            "seats_release_only": new_seats.join(old_seats, on=seat, how="anti").height,
            "seats_reservation_differs": labels.height,
            "reservation_examples": labels.head(examples).to_dicts(),
            "legacy_only_examples": only_old.head(examples).to_dicts(),
            "release_only_examples": only_new.head(examples).to_dicts(),
        }
        if only_old.height or only_new.height:
            flags.append(f"legacy_differs_{office}")
        if labels.height:
            flags.append(f"legacy_reservation_differs_{office}")
    return report, flags


def compare_frame(seats, frame):
    expected = frame.group_by("office").len("frame")
    found = seats.group_by("office").len("release")
    diff = expected.join(found, on="office", how="full", coalesce=True).filter(
        pl.col("frame") != pl.col("release").fill_null(0)
    )
    empty = (
        seats.group_by("office", "district")
        .agg(
            pl.len().alias("seats"),
            (pl.col("status") == "no_record").sum().alias("no_record"),
        )
        .with_columns(share=pl.col("no_record") / pl.col("seats"))
    )
    report = {
        "seats": dict(found.sort("office").iter_rows()),
        "office_mismatches": diff.to_dicts(),
        "no_record_by_office": dict(
            seats.filter(pl.col("status") == "no_record")
            .group_by("office")
            .len()
            .sort("office")
            .iter_rows()
        ),
        # A district with no records at all points at a failed cascade, not at
        # an election without candidates.
        "districts_mostly_no_record": empty.filter(pl.col("share") > 0.5)
        .sort("share", descending=True)
        .to_dicts(),
    }
    flags = ["frame_office_counts"] if diff.height else []
    if report["districts_mostly_no_record"]:
        flags.append("districts_mostly_no_record")
    return report, flags


def consistency(seats, candidates, winners, examples=20):
    people = candidates.filter(pl.col("remarks") != "Vacant").join(
        seats.unique(KEY, keep="first").select(*KEY, "seat_reservation"),
        on=KEY,
        how="left",
        nulls_equal=True,
    )
    reserved = people.filter(pl.col("seat_reservation").is_not_null())
    base = pl.col("seat_reservation").str.replace(WOMEN, "", literal=True)
    men = reserved.filter(
        pl.col("seat_reservation").str.contains(WOMEN, literal=True)
        & (pl.col("gender") != "female")
    )
    category = reserved.filter(
        base.is_in(list(SEAT_CATEGORY)) & (pl.col("category") != base)
    )
    per_seat = candidates.group_by(KEY).agg(
        pl.len().alias("rows"),
        (pl.col("remarks") == "Uncontested").sum().alias("uncontested"),
        (pl.col("remarks") == "Vacant").sum().alias("vacant"),
        pl.col("page").max().alias("last_page"),
    )
    paging = per_seat.filter(
        pl.col("last_page") != ((pl.col("rows") - 1) // PAGE_SIZE + 1)
    )
    columns = [*KEY, "sr_no", "candidate_name", "gender_raw", "category"]
    report = {
        "non_female_candidates_in_women_seats": men.height,
        "non_female_examples": men.select(*columns, "seat_reservation")
        .head(examples)
        .to_dicts(),
        "other_category_in_sc_st_seats": category.height,
        "other_category_examples": category.select(*columns, "seat_reservation")
        .head(examples)
        .to_dicts(),
        "reservation_by_candidate_category": reserved.group_by(
            base.alias("seat"), "category"
        )
        .len()
        .sort("seat", "len", descending=[False, True])
        .to_dicts(),
        "uncontested_with_other_rows": per_seat.filter(
            (pl.col("uncontested") > 0) & (pl.col("rows") > pl.col("uncontested"))
        ).height,
        "vacant_with_other_rows": per_seat.filter(
            (pl.col("vacant") > 0) & (pl.col("rows") > pl.col("vacant"))
        ).height,
        "rows_not_matching_page_count": paging.height,
        "winner_note": dict(
            seats.group_by("winner_note").len().sort("winner_note").iter_rows()
        ),
        "winners_by_basis": dict(winners.group_by("winner_basis").len().iter_rows()),
        "tied_top_vote": winners.filter(
            pl.col("tied") & (pl.col("winner_basis") == "top_vote")
        ).height,
        # Expected zero: a seat with a candidate and no note names a winner.
        "contested_seats_without_winner": seats.filter(pl.col("winner_note").is_null())
        .join(people.select(KEY).unique(), on=KEY, nulls_equal=True)
        .join(winners, on=KEY, how="anti", nulls_equal=True)
        .height,
    }
    flags = ["rows_not_matching_page_count"] if paging.height else []
    return report, flags


def nfc(column):
    return pl.col(column).map_elements(
        lambda text: unicodedata.normalize("NFC", text), return_dtype=pl.Utf8
    )


def roster_office(name):
    name = name.lower()
    if "pramukh" in name:
        return None
    return next((v for k, v in ROSTER_OFFICES.items() if k in name), None)


def compare_roster(seats, roster, examples=20):
    """The SEC's reservation roster PDFs against the form's reservation label.

    Only rosters with a text layer are read (others are scans). Zila parishad seats
    are numbered within the district, so they are compared seat by seat; the other
    rosters name blocks in a legacy font encoding, so they are compared as counts
    of each label in districts where the roster lists as many seats as the form.
    """
    roster = roster.with_columns(
        pl.col("office").map_elements(roster_office, return_dtype=pl.Utf8),
        pl.col("district_button").replace(ROSTER_DISTRICTS).alias("name"),
        label=pl.col("category")
        + pl.when(pl.col("women") == "महिला").then(pl.lit(WOMEN)).otherwise(pl.lit("")),
    ).filter(pl.col("office").is_not_null())
    roster = roster.unique(["office", "name", "block_krutidev", "seat_no", "label"])
    # The form writes ड़ as one code point and the roster table as two.
    roster = roster.with_columns(nfc("label"))
    mine = seats.with_columns(
        pl.col("district").str.split(" - ").list.get(1).alias("name"),
        nfc("seat_reservation"),
    )
    zila = "zila_parishad_member"
    pairs = (
        mine.filter(pl.col("office") == zila)
        # A few seat codes carry trailing spaces ("40 ").
        .with_columns(
            pl.col("unit_code").str.strip_chars().cast(pl.Int64).alias("seat_no")
        )
        .join(roster.filter(pl.col("office") == zila), on=["name", "seat_no"])
    )
    differs = pairs.filter(
        pl.col("seat_reservation").is_not_null()
        & (pl.col("seat_reservation") != pl.col("label"))
    )
    counted = []
    for office in ("panchayat_samiti_member", "mukhiya", "sarpanch"):
        theirs = roster.filter(pl.col("office") == office)
        ours = mine.filter(pl.col("office") == office)
        sizes = (
            theirs.group_by("name")
            .len("roster")
            .join(ours.group_by("name").len("release"), on="name")
        )
        full = sizes.filter(pl.col("roster") == pl.col("release"))["name"]
        tally = (
            theirs.filter(pl.col("name").is_in(full.to_list()))
            .group_by("name", "label")
            .len("roster")
            .join(
                ours.filter(pl.col("name").is_in(full.to_list()))
                .group_by("name", pl.col("seat_reservation").alias("label"))
                .len("release"),
                on=["name", "label"],
                how="full",
                coalesce=True,
            )
            .fill_null(0)
        )
        counted.append(
            {
                "office": office,
                "districts_with_roster_text": sizes.height,
                "districts_with_equal_seat_counts": full.len(),
                "seats_compared": int(tally["roster"].sum()),
                # Half the summed gaps: seats that would have to change label.
                "seats_off": int((tally["roster"] - tally["release"]).abs().sum() // 2),
                "release_without_label": int(
                    tally.filter(pl.col("label").is_null())["release"].sum()
                ),
            }
        )
    report = {
        "zila_parishad_seats_compared": pairs.height,
        "zila_parishad_seats_differing": differs.height,
        "zila_parishad_examples": differs.select(
            "district", "unit_code", "seat_reservation", pl.col("label").alias("roster")
        )
        .head(examples)
        .to_dicts(),
        "label_counts": counted,
    }
    return report, (["roster_differs_zila_parishad"] if differs.height else [])


def distributions(seats, candidates, winners):
    top = candidates.sort("votes", descending=True, nulls_last=True).head(10)
    return {
        "candidates_by_office": dict(
            candidates.group_by("office").len().sort("office").iter_rows()
        ),
        "candidates_per_seat": dict(
            seats.group_by("candidate_rows").len().sort("candidate_rows").iter_rows()
        ),
        "gender_raw": dict(candidates.group_by("gender_raw").len().iter_rows()),
        "remarks": dict(candidates.group_by("remarks").len().iter_rows()),
        "category": dict(candidates.group_by("category").len().iter_rows()),
        "education": dict(candidates.group_by("education").len().iter_rows()),
        "seat_reservation": dict(seats.group_by("seat_reservation").len().iter_rows()),
        "age_quantiles": candidates.select(
            pl.col("age").quantile(q).alias(str(q)) for q in (0, 0.01, 0.5, 0.99, 1)
        ).to_dicts()[0],
        "age_under_21": candidates.filter(pl.col("age") < 21).height,
        "age_unusable": candidates.filter(
            pl.col("age").is_null() & pl.col("age_raw").is_not_null()
        )["age_raw"].to_list()[:20],
        "sr_no_repeated_rows": candidates.filter("sr_no_repeated").height,
        "won_by_lot": candidates.filter("won_by_lot").height,
        "top_votes": top.select(*KEY, "candidate_name", "votes").to_dicts(),
        "winner_margin_quantiles": winners.select(
            pl.col("margin").quantile(q).alias(str(q)) for q in (0, 0.5, 0.99, 1)
        ).to_dicts()[0],
    }


class Form:
    """The results form requested with urllib; shares no code with sec_2016."""

    def __init__(self):
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar)
        )
        self.opener.addheaders = [("User-Agent", AGENT)]

    def send(self, soup=None, **fields):
        data = None
        if soup is not None:
            values = {
                i["name"]: i.get("value", "")
                for i in soup.select("input[type=hidden][name]")
            }
            for select in soup.select("select[name]"):
                chosen = select.select_one("option[selected]") or select.select_one(
                    "option"
                )
                values[select["name"]] = chosen.get("value", "") if chosen else ""
            values.update(fields)
            data = urllib.parse.urlencode(values).encode()
        for attempt in range(RETRIES):
            try:
                with self.opener.open(URL, data=data, timeout=180) as response:
                    html = response.read().decode("utf-8")
                return BeautifulSoup(html, "html.parser")
            except (urllib.error.URLError, TimeoutError):
                if attempt == RETRIES - 1:
                    raise
                time.sleep(30 * (attempt + 1))

    def choose(self, soup, field, value):
        return self.send(soup, **{field: value, "__EVENTTARGET": field})

    def first_page(self, seat):
        office = OFFICE_CODES[seat["office"]]
        soup = self.choose(self.send(), "ddlPostName", office)
        soup = self.choose(soup, "ddlDistrict", seat["district_code"])
        if seat["block_code"]:
            soup = self.choose(soup, "ddlBlok", seat["block_code"])
        if seat["panchayat_code"]:
            soup = self.choose(soup, "ddlPanchayat", seat["panchayat_code"])
        soup = self.send(
            soup,
            **{LAST_FIELD[office]: seat["unit_code"], "btnSubmit": "View"},
            __EVENTTARGET="",
        )
        grid = soup.select_one("#gvVoterListDetails")
        if grid is None:
            return []
        cells = [
            [td.get_text(" ", strip=True) for td in tr.find_all("td", recursive=False)]
            for tr in grid.select("tr")[1:]
        ]
        return [c for c in cells if len(c) == 12]


def refetch(seats, candidates, sample, seed):
    pool = seats.filter(~pl.col("code_repeated")).unique(KEY).sort(KEY)
    picks = pool.sample(min(sample, pool.height), seed=seed).to_dicts()
    random.Random(seed).shuffle(picks)
    form, differing = Form(), []
    for seat in picks:
        live = form.first_page(seat)
        saved = candidates.filter(
            pl.all_horizontal(pl.col(k).eq_missing(pl.lit(seat[k])) for k in KEY)
            & (pl.col("page") == 1)
        ).sort("row")
        mine = [
            [
                (r["candidate_name"] or ""),
                (r["votes_raw"] or ""),
                r["remarks"],
            ]
            for r in saved.to_dicts()
        ]
        theirs = [[c[1], c[10], c[11]] for c in live]
        theirs = [["" if v == "--" else v for v in row] for row in theirs]
        mine = [["" if v == "--" else v for v in row] for row in mine]
        if mine != theirs:
            differing.append(
                {"seat": {k: seat[k] for k in KEY}, "live": theirs, "saved": mine}
            )
    report = {"seats_requested": len(picks), "differing": differing}
    return report, (["refetch_differs"] if differing else [])


def audit(release, frame_path, legacy, roster, sample, seed):
    seats = pl.read_parquet(release / "seats.parquet")
    candidates = pl.read_parquet(release / "candidates.parquet")
    winners = pl.read_parquet(release / "winners.parquet")
    frame = pl.from_arrow(pq.read_table(frame_path))
    report, flags = {}, []
    sections = {
        "seats_vs_frame": lambda: compare_frame(seats, frame),
        "legacy_files": lambda: compare_legacy(seats, candidates, legacy),
        "consistency": lambda: consistency(seats, candidates, winners),
        "roster": lambda: compare_roster(seats, pl.read_parquet(roster)),
        "refetch": lambda: refetch(seats, candidates, sample, seed),
    }
    for name, section in sections.items():
        if name == "refetch" and not sample:
            continue
        report[name], found = section()
        flags += found
    report["distributions"] = distributions(seats, candidates, winners)
    report["flags"] = flags
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release", type=Path, default=Path("data/release/2016_panchayat")
    )
    parser.add_argument(
        "--frame", type=Path, default=Path("data/raw/statewide_2016/2016/frame.parquet")
    )
    parser.add_argument("--legacy", type=Path, default=Path("data/fin"))
    parser.add_argument(
        "--roster",
        type=Path,
        default=Path("data/interim/2016/reservation_roster.parquet"),
    )
    parser.add_argument("--refetch", type=int, default=30)
    parser.add_argument("--seed", type=int, default=2016)
    args = parser.parse_args()
    report = audit(
        args.release, args.frame, args.legacy, args.roster, args.refetch, args.seed
    )
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    (args.release / "audit.json").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()

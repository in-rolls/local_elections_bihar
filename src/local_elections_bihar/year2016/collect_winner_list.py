"""Collect the SEC's 2016 Mukhiya winner list (old-sec/wcl.aspx) for chosen blocks.

wcl.aspx cascades post -> district -> block like ovc.aspx, and a View lists one
winner per panchayat of the block: names, gender, age, category, seat reservation,
education, contact and an affidavit link, but no votes. It is collected for two
sets of blocks: those where ovc.aspx answered "Record not Found" for some Mukhiya
seat, to see whether this list fills them, and those holding a seat whose ovc.aspx
rows name no winner, as evidence for adjudicating it. Requests are sequential and
spaced; each block's responses go in one ledger, and finished ledgers are reused.
"""

import argparse
import json
import re
import time
from pathlib import Path

import polars as pl
from bs4 import BeautifulSoup

from local_elections_bihar.year2016.collect import (
    Ledger,
    form_state,
    postback,
    record,
    request,
)

URL = "https://sec.bihar.gov.in/old-sec/wcl.aspx"
MUKHIYA = "0107"
GRID = "gvMukhiyaSarpanch"
# Seconds between requests; the server is a small state-government host.
DELAY = 2.5
# Version 2 follows the grid's pager; version-1 ledgers kept page 1 only.
VERSION = 2
PAGE_LINK = re.compile(rf"__doPostBack\('{GRID}','Page\$(\d+)'\)")


def paced(function, *args, **kwargs):
    time.sleep(DELAY)
    return function(*args, **kwargs, url=URL)


def target_blocks(seats_path):
    """(district, block) pairs with a no-record or no-winner Mukhiya seat."""
    seats = pl.read_parquet(seats_path).filter(pl.col("office") == "mukhiya")
    wanted = seats.filter(
        (pl.col("status") == "no_record") | pl.col("winner_note").is_not_null()
    )
    return sorted(set(wanted.select("district_code", "block_code").iter_rows()))


def ledger_path(raw, district, block):
    return raw / f"2016/winner_list/mukhiya_d{district}_b{block}.jsonl.gz"


def collect(raw, blocks):
    by_district = {}
    for district, block in blocks:
        if Ledger(ledger_path(raw, district, block)).completed(VERSION) is None:
            by_district.setdefault(district, []).append(block)
    for district, pending in sorted(by_district.items()):
        page = paced(request, "GET")
        page = paced(postback, page, "ddlPostName", MUKHIYA)
        page = paced(postback, page, "ddlDistrict", district)
        offered = {v for v, _ in form_state(page)[1]["ddlBlok"]}
        for block in pending:
            if block not in offered:
                raise ValueError(f"Block {block} not offered for district {district}")
            values = {"post": MUKHIYA, "district": district, "block": block}
            chosen = paced(postback, page, "ddlBlok", block)
            view = paced(postback, chosen, "ddlBlok", block, submit=True)
            events = [
                record("block", values, chosen),
                record("view", {**values, "page": 1}, view),
            ]
            for number, html in later_pages(view).items():
                events.append(record("view", {**values, "page": number}, html))
            Ledger(ledger_path(raw, district, block)).write(events, VERSION)
            print(json.dumps({**values, "pages": len(events) - 1}), flush=True)


def current_page(html):
    """Page number the winner grid shows as selected (1 when unpaged)."""
    grid = BeautifulSoup(html, "html.parser").select_one(f"#{GRID}")
    pager = grid.select("tr td table span") if grid else []
    return int(pager[0].get_text(strip=True)) if pager else 1


def later_pages(first):
    """The winner grid's pages after the first, requested through its pager."""
    pages, html = {}, first
    while True:
        links = BeautifulSoup(html, "html.parser").select(f"#{GRID} a[href]")
        numbers = {int(n) for a in links for n in PAGE_LINK.findall(a["href"])}
        targets = sorted(numbers - {1} - set(pages))
        if not targets:
            return pages
        target = targets[0]
        hidden, _, chosen = form_state(html)
        data = {
            **hidden,
            **chosen,
            "__EVENTTARGET": GRID,
            "__EVENTARGUMENT": f"Page${target}",
        }
        html = paced(request, "POST", data)
        if current_page(html) != target:
            raise ValueError(f"Requested page {target}, got {current_page(html)}")
        pages[target] = html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/2016/statewide"))
    parser.add_argument(
        "--seats", type=Path, default=Path("data/release/2016/seats.parquet")
    )
    parser.add_argument(
        "--blocks", nargs="*", help="DISTRICT:BLOCK codes; default: derived from seats"
    )
    args = parser.parse_args()
    blocks = (
        [tuple(b.split(":")) for b in args.blocks]
        if args.blocks
        else target_blocks(args.seats)
    )
    print(json.dumps({"blocks": len(blocks)}))
    collect(args.raw, blocks)


if __name__ == "__main__":
    main()

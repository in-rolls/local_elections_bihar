"""Collect the official Patna municipal winner lists and supporting documents."""

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from local_elections_bihar.year2016.collect import form_state

RAW = Path("data/raw/urban/patna")
OLD = "https://sec.bihar.gov.in/old-sec/UWCL.aspx"
BASE = "http://sec2021.bihar.gov.in/SEC_NP_P2_01/"
WINNERS = BASE + "Admin/WinningCandidatesPost_Wise.aspx"
PARAMS = {"district_id": 28, "subdivision_id": -1, "post_id": 3, "npid": 310}


def digest(body):
    return hashlib.sha256(body).hexdigest()


class Collector:
    def __init__(self, raw):
        self.raw = raw
        raw.mkdir(parents=True, exist_ok=True)
        self.receipts = raw / "receipts.jsonl"
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; local-elections-bihar research archive)"
        )
        retries = Retry(
            total=3, backoff_factor=2, status_forcelist=[429, 502, 503, 504]
        )
        self.session.mount("http://", HTTPAdapter(max_retries=retries))
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def fetch(self, name, url, *, data=None, payload=None):
        path = self.raw / name
        records = (
            [json.loads(line) for line in self.receipts.read_text().splitlines()]
            if self.receipts.exists()
            else []
        )
        for receipt in reversed(records):
            if receipt["file"] == name and receipt["ok"] and path.exists():
                body = path.read_bytes()
                if digest(body) == receipt["sha256"]:
                    return body
        time.sleep(1)
        method = "POST" if data is not None or payload is not None else "GET"
        response = self.session.request(
            method, url, data=data, json=payload, timeout=(20, 90)
        )
        body = response.content
        ok = response.ok and "/Error.aspx" not in response.url
        receipt = {
            "file": name,
            "url": url,
            "response_url": response.url,
            "method": method,
            "parameters": payload
            or {k: v for k, v in (data or {}).items() if not k.startswith("__")},
            "request_body_sha256": digest(str(response.request.body).encode()),
            "retrieved_at_utc": datetime.now(UTC).isoformat(),
            "server_date": response.headers.get("Date"),
            "http_status": response.status_code,
            "content_type": response.headers.get("Content-Type"),
            "sha256": digest(body),
            "bytes": len(body),
            "ok": ok,
        }
        if ok:
            temp = path.with_suffix(path.suffix + ".part")
            temp.write_bytes(body)
            temp.replace(path)
        else:
            receipt["error_body"] = response.text
        with self.receipts.open("a") as handle:
            handle.write(json.dumps(receipt, ensure_ascii=False) + "\n")
        response.raise_for_status()
        if not ok:
            raise ValueError(f"Not a source response: {response.url}")
        print(json.dumps({"file": name, "bytes": len(body)}), flush=True)
        return body


def collect(raw):
    collector = Collector(raw)
    collector.fetch("winners_2022_form.html", WINNERS)
    collector.fetch("controls_2022.js", BASE + "assets/js/ControlNP1.min.js")
    body = collector.fetch(
        "winners_2022.json", WINNERS + "/GetWinningCandidtes", payload=PARAMS
    )
    records = json.loads(json.loads(body)["d"])
    if len(records) != 75 or {r["wardno"] for r in records} != set(range(1, 76)):
        raise ValueError("Incomplete 2022 Patna winner frame")
    body = collector.fetch("winners_2017_form.html", OLD)
    hidden, _, chosen = form_state(body)
    body = collector.fetch(
        "winners_2017_district.html",
        OLD,
        data={**hidden, **chosen, "ddlDistrict": "28", "__EVENTTARGET": "ddlDistrict"},
    )
    hidden, options, chosen = form_state(body)
    if ("280401301", "Patna Nagar Nigam") not in options["ddlPanchayat"]:
        raise ValueError("Patna corporation absent from 2017 form")
    body = collector.fetch(
        "winners_2017_page1.html",
        OLD,
        data={
            **hidden,
            **chosen,
            "ddlPanchayat": "280401301",
            "btnSubmit": "View",
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
        },
    )
    for number in range(2, 5):
        hidden, _, chosen = form_state(body)
        body = collector.fetch(
            f"winners_2017_page{number}.html",
            OLD,
            data={
                **hidden,
                **chosen,
                "__EVENTTARGET": "gvWard",
                "__EVENTARGUMENT": f"Page${number}",
            },
        )
        selected = BeautifulSoup(body, "html.parser").select("#gvWard tr td table span")
        if len(selected) != 1 or selected[0].get_text(strip=True) != str(number):
            raise ValueError(f"Winner pager did not reach page {number}")
    for name, url in {
        "archive.html": "https://sec.bihar.gov.in/SECOfficial/archiveNP.aspx",
        "reservation_2017.html": "https://sec.bihar.gov.in/old-sec/ULBReservation.aspx",
        "reservation_2017.pdf": (
            "https://sec.bihar.gov.in/old-sec/Reservation/ULBReservation/Patna.pdf"
        ),
        "reservation_process_2022.pdf": (
            "https://sec.bihar.gov.in/Documents/Instruction_Letters/Reservation%20Process.pdf"
        ),
        "election_schedule_2017.pdf": (
            "https://sec.bihar.gov.in/old-sec/letters/Letter%201557.pdf"
        ),
    }.items():
        body = collector.fetch(name, url)
        if name.endswith(".pdf") and not body.startswith(b"%PDF"):
            raise ValueError(f"Invalid PDF: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=RAW)
    collect(parser.parse_args().raw)


if __name__ == "__main__":
    main()

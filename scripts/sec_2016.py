"""Re-collect 2016 panchayat results from the SEC's archived ASP.NET form.

The form at old-sec/ovc.aspx cascades office -> district -> block -> panchayat ->
ward (or territorial number). Each dropdown change is a postback whose response
carries the next dropdown, so work is organised in units that replay their own
cascade: one ledger per office and district for the frame, and one per office,
district and block for results. Every response's HTML is saved in the ledger.
"""

import argparse
import base64
import concurrent.futures
import gzip
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from bs4 import BeautifulSoup
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_delay,
    wait_exponential,
)

URL = "https://sec.bihar.gov.in/old-sec/ovc.aspx"
# The form answers postbacks from clients it does not recognise as browsers with
# HTTP 500 (ASP.NET browser capabilities); a Mozilla-compatible agent still names us.
AGENT = "Mozilla/5.0 (compatible; local-elections-bihar research archive)"
OFFICES = {
    "0102": "zila_parishad_member",
    "0105": "panchayat_samiti_member",
    "0107": "mukhiya",
    "0108": "sarpanch",
    "0109": "ward_member",
    "0110": "panch",
}
LAST = {
    "0102": "ddlPradesik",
    "0105": "ddlPradesik",
    "0107": "ddlPanchayat",
    "0108": "ddlPanchayat",
    "0109": "ddlWard",
    "0110": "ddlWard",
}
LOCAL = threading.local()


class Transient(Exception):
    pass


def session():
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        LOCAL.session.headers["User-Agent"] = AGENT
    return LOCAL.session


def form_state(html):
    soup = BeautifulSoup(html, "html.parser")
    hidden = {
        i["name"]: i.get("value", "") for i in soup.select("input[type=hidden][name]")
    }
    options, chosen = {}, {}
    for select in soup.select("select[name]"):
        values = [
            (o.get("value"), o.get_text(strip=True)) for o in select.select("option")
        ]
        options[select["name"]] = [(v, t) for v, t in values if v not in ("", "0")]
        first = select.select_one("option[selected]") or select.select_one("option")
        chosen[select["name"]] = first.get("value", "") if first else ""
    return hidden, options, chosen


def request(method, data=None):
    def attempt():
        try:
            if method == "GET":
                response = session().get(URL, timeout=(30, 180))
            else:
                response = session().post(URL, data=data, timeout=(30, 180))
        except (requests.ConnectionError, requests.Timeout) as error:
            raise Transient(str(error)) from error
        if response.status_code == 429 or response.status_code >= 500:
            raise Transient(f"HTTP {response.status_code}")
        response.raise_for_status()
        if "__VIEWSTATE" not in response.text:
            raise Transient("Response is not the results form")
        return response.text

    policy = Retrying(
        retry=retry_if_exception_type(Transient),
        stop=stop_after_delay(3600),
        wait=wait_exponential(multiplier=5, max=600),
        reraise=True,
    )
    return policy(attempt)


def postback(html, field, value, submit=False):
    hidden, _, chosen = form_state(html)
    data = {**hidden, **chosen, field: value}
    if submit:
        data.update(__EVENTTARGET="", __EVENTARGUMENT="", btnSubmit="View")
    else:
        data.update(__EVENTTARGET=field, __EVENTARGUMENT="")
    return request("POST", data)


class Ledger:
    """One gzipped JSONL per unit; a unit counts only once its done line exists."""

    def __init__(self, path):
        self.path = path

    def completed(self):
        try:
            with gzip.open(self.path, "rt", encoding="utf-8") as stream:
                rows = [json.loads(line) for line in stream]
        except (FileNotFoundError, EOFError, OSError, ValueError):
            return None
        return rows[:-1] if rows and rows[-1].get("done") else None

    def write(self, events):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".part")
        with gzip.open(temp, "wt", encoding="utf-8") as stream:
            for event in events:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.write(json.dumps({"done": True, "at": now()}) + "\n")
        temp.replace(self.path)


def now():
    return datetime.now(UTC).isoformat()


def record(step, values, html):
    return {
        "step": step,
        **values,
        "fetched_at": now(),
        "html_gzip_base64": base64.b64encode(gzip.compress(html.encode())).decode(),
    }


def html_of(event):
    return gzip.decompress(base64.b64decode(event["html_gzip_base64"])).decode()


def district_page(office, district):
    page = request("GET")
    page = postback(page, "ddlPostName", office)
    return postback(page, "ddlDistrict", district)


def frame_unit(raw, office, district):
    ledger = Ledger(raw / f"2016/frame/{OFFICES[office]}_d{district}.jsonl.gz")
    if ledger.completed() is not None:
        return {"office": office, "district": district, "cached": True}
    events = []
    page = district_page(office, district)
    events.append(record("district", {"office": office, "district": district}, page))
    if office == "0102":
        ledger.write(events)
        return {"office": office, "district": district, "events": len(events)}
    for block, _ in form_state(page)[1]["ddlBlok"]:
        block_page = postback(page, "ddlBlok", block)
        values = {"office": office, "district": district, "block": block}
        events.append(record("block", values, block_page))
        if office in ("0109", "0110"):
            for panchayat, _ in form_state(block_page)[1]["ddlPanchayat"]:
                panchayat_page = postback(block_page, "ddlPanchayat", panchayat)
                events.append(
                    record(
                        "panchayat", {**values, "panchayat": panchayat}, panchayat_page
                    )
                )
    ledger.write(events)
    return {"office": office, "district": district, "events": len(events)}


def frame_rows(raw):
    rows = []
    for path in sorted((raw / "2016/frame").glob("*.jsonl.gz")):
        events = Ledger(path).completed()
        if events is None:
            raise ValueError(f"Incomplete frame unit: {path}")
        pages = {}
        for event in events:
            _, options, _ = form_state(html_of(event))
            pages[(event["step"], event.get("block"), event.get("panchayat"))] = (
                options,
                event,
            )
        for (step, block, panchayat), (options, event) in pages.items():
            office = event["office"]
            last = LAST[office]
            parent = {
                "district": office in ("0102",),
                "block": office in ("0105", "0107", "0108"),
                "panchayat": office in ("0109", "0110"),
            }
            if not parent[step]:
                continue
            names = {k: dict(v) for k, v in options.items()}
            for value, label in options.get(last, []):
                rows.append(
                    {
                        "office": OFFICES[office],
                        "office_code": office,
                        "district": event["district"],
                        "district_label": names["ddlDistrict"].get(event["district"]),
                        "block": block,
                        "block_label": names.get("ddlBlok", {}).get(block),
                        "panchayat": panchayat,
                        "panchayat_label": names.get("ddlPanchayat", {}).get(panchayat),
                        "unit": value,
                        "unit_label": label,
                    }
                )
    return rows


def build_frame(raw, workers):
    office_page = postback(request("GET"), "ddlPostName", "0107")
    districts = [v for v, _ in form_state(office_page)[1]["ddlDistrict"]]
    if len(districts) != 38:
        raise ValueError(f"Expected 38 districts, found {len(districts)}")
    jobs = [(office, d) for office in OFFICES for d in districts]
    run_jobs(lambda job: frame_unit(raw, *job), jobs, workers)
    rows = frame_rows(raw)
    keys = [
        (r["office"], r["district"], r["block"], r["panchayat"], r["unit"])
        for r in rows
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("Repeated unit in 2016 frame")
    pq.write_table(pa.Table.from_pylist(rows), raw / "2016/frame.parquet")
    counts = {}
    for r in rows:
        counts[r["office"]] = counts.get(r["office"], 0) + 1
    print(json.dumps({"units": counts}))


def results_unit(raw, office, district, block, units):
    """View every unit under one block (or district, for zila parishad)."""
    if any(
        (u["office_code"], u["district"], u["block"]) != (office, district, block)
        for u in units
    ):
        raise ValueError("Units outside the requested office, district and block")
    name = f"{OFFICES[office]}_d{district}" + (f"_b{block}" if block else "")
    ledger = Ledger(raw / f"2016/results/{name}.jsonl.gz")
    if ledger.completed() is not None:
        return {"unit": name, "cached": True}
    events = []
    page = district_page(office, district)
    if block:
        page = postback(page, "ddlBlok", block)
    by_panchayat = {}
    for u in units:
        by_panchayat.setdefault(u["panchayat"], []).append(u)
    for panchayat, group in by_panchayat.items():
        parent = page
        if office in ("0109", "0110"):
            parent = postback(page, "ddlPanchayat", panchayat)
        for u in group:
            result = postback(parent, LAST[office], u["unit"], submit=True)
            values = {
                k: u[k]
                for k in ("office_code", "district", "block", "panchayat", "unit")
            }
            events.append(record("view", values, result))
    ledger.write(events)
    return {"unit": name, "views": len(events)}


def collect_results(raw, workers, offices):
    frame = pq.read_table(raw / "2016/frame.parquet").to_pylist()
    groups = {}
    for u in frame:
        if u["office_code"] in offices:
            key = (u["office_code"], u["district"], u["block"])
            groups.setdefault(key, []).append(u)
    jobs = sorted(groups.items(), key=lambda item: hash(item[0]) % 9973)
    run_jobs(lambda job: results_unit(raw, *job[0], job[1]), jobs, workers)


def run_jobs(function, jobs, workers):
    failed = 0
    start = time.monotonic()

    def run(job):
        try:
            return function(job)
        except Exception as error:
            return {"job": str(job)[:120], "error": f"{type(error).__name__}: {error}"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for done, result in enumerate(pool.map(run, jobs), 1):
            failed += "error" in result
            live = sum(
                t.name.startswith("ThreadPoolExecutor") for t in threading.enumerate()
            )
            print(
                json.dumps(
                    {
                        "at": now()[11:19],
                        "done": done,
                        "of": len(jobs),
                        "failed": failed,
                        "workers_live": live,
                        "minutes": round((time.monotonic() - start) / 60, 1),
                        **result,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    if failed:
        raise SystemExit(f"{failed} units failed; rerun to retry them")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["frame", "results"])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/statewide_2016"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--offices", nargs="+", default=list(OFFICES))
    args = parser.parse_args()
    if args.stage == "frame":
        build_frame(args.raw, args.workers)
    else:
        collect_results(args.raw, args.workers, set(args.offices))


if __name__ == "__main__":
    main()

"""Write data/raw/fetch_log.csv: one row per tracked raw file (in-rolls docs/layout.md).

    python -m local_elections_bihar.build.fetch_log          # write
    python -m local_elections_bihar.build.fetch_log --check  # compare only

Three kinds of raw file are tracked. The SEC documents were copied byte-identical
from in-rolls/local_elections; their MANIFEST.json names each original path, so
the row is `method=copy` with `copied_from`, and `url` stays blank because no
one recorded where the documents were downloaded. The 2016 winner-list ledgers
were saved by collect_winner_list from the SEC portal; each response line keeps
its own `fetched_at`, and the row gives the earliest. The originals restored
from the Zenodo archives are not tracked and have no row; PROVENANCE.json
records those archives. Pages of Bihar's old government sites came from the
Wayback Machine (collect/wayback.py); each has a receipt in
data/search_log/<host>_wayback.jsonl, so the row is `method=wayback` with the
capture's URL and the time it was saved.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

from local_elections_bihar.paths import SEARCH_LOG
from local_elections_bihar.year2016.collect_winner_list import URL as WINNER_LIST_URL

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
LOG = RAW / "fetch_log.csv"
DOCUMENTS = RAW / "sec_documents"
WINNER_LIST = RAW / "2016" / "statewide" / "2016" / "winner_list"
COLUMNS = ["path", "url", "sha256", "bytes", "fetched_at_utc", "method", "copied_from"]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tracked():
    out = subprocess.run(
        ["git", "ls-files", "-z", "data/raw"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [ROOT / p for p in out.decode().split("\0") if p]


def earliest_fetch(ledger):
    with gzip.open(ledger, "rt", encoding="utf-8") as stream:
        times = [json.loads(line).get("fetched_at") for line in stream]
    return min(t for t in times if t)


def rows():
    manifest = json.loads((DOCUMENTS / "MANIFEST.json").read_text(encoding="utf-8"))
    copied = {item["path"]: item for item in manifest["files"]}
    commit = manifest["origin_commit"]
    receipts = {}
    for log in sorted(SEARCH_LOG.glob("*_wayback.jsonl")):
        for line in log.read_text(encoding="utf-8").splitlines():
            receipt = json.loads(line)
            receipts[receipt["path"]] = receipt
    out = []
    for path in tracked():
        if path == LOG:
            continue
        sha = digest(path)
        row = {
            "path": path.relative_to(ROOT).as_posix(),
            "url": "",
            "sha256": sha,
            "bytes": path.stat().st_size,
            "fetched_at_utc": "",
            "method": "unknown",
            "copied_from": "",
        }
        if path.is_relative_to(DOCUMENTS):
            item = copied.get(path.relative_to(DOCUMENTS).as_posix())
            if item is None:
                row["method"] = "manual"  # the folder's own README and MANIFEST
            else:
                if item["sha256"] != sha:
                    raise SystemExit(f"{row['path']}: differs from its MANIFEST")
                row["method"] = "copy"
                row["copied_from"] = (
                    f"in-rolls/local_elections@{commit}:{item['original_path']}"
                )
        elif row["path"] in receipts:
            receipt = receipts[row["path"]]
            if receipt["sha256"] != sha:
                raise SystemExit(f"{row['path']}: differs from its Wayback receipt")
            row["url"] = receipt["url"]
            row["fetched_at_utc"] = receipt["fetched_at_utc"]
            row["method"] = "wayback"
        elif path.parent == WINNER_LIST:
            row["url"] = WINNER_LIST_URL
            row["fetched_at_utc"] = earliest_fetch(path)
            row["method"] = "live"
        out.append(row)
    return sorted(out, key=lambda r: r["path"])


def render(table):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(table)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description="Write the raw-file fetch log.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = render(rows())
    name = LOG.relative_to(ROOT)
    if args.check:
        if not LOG.exists() or LOG.read_text(encoding="utf-8") != text:
            print(f"{name} is out of date; run without --check")
            return 1
        print(f"{name}: up to date")
        return 0
    LOG.write_text(text, encoding="utf-8")
    print(f"wrote {name} ({text.count(chr(10)) - 1} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

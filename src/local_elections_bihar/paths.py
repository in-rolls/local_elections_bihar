"""Every data folder, named once (in-rolls docs/layout.md)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
RELEASE = DATA / "release"
SEARCH_LOG = DATA / "search_log"
CHECKS = DATA / "checks"

SEC_DOCUMENTS = RAW / "sec_documents"
SEC_SITE = RAW / "sec_bih_nic_in"
SEC_SITE_RECEIPTS = SEARCH_LOG / "sec_bih_nic_in_wayback.jsonl"

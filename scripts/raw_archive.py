"""Pack, verify and index this state's raw-data archive.

    python scripts/raw_archive.py index   # (re)write data/raw_archive/MANIFEST.csv
    python scripts/raw_archive.py verify  # check the files against MANIFEST.csv
    python scripts/raw_archive.py pack    # dist/raw_archive/<repo>_raw_<date>.tar.gz

Raw source material is too large for git, so it lives in data/raw_archive/,
git-ignored except for MANIFEST.csv and README.md, and is shared as a tarball
(on Google Drive; the link is in README.md). MANIFEST.csv is the contract: a
download is correct only if `verify` passes on it.
"""

import argparse
import csv
import datetime
import hashlib
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data" / "raw_archive"
MANIFEST = ARCHIVE / "MANIFEST.csv"
TRACKED = {"MANIFEST.csv", "README.md"}
JUNK = {".DS_Store", "Desktop.ini", "Thumbs.db"}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def archived_files():
    for path in sorted(ARCHIVE.rglob("*")):
        relative = path.relative_to(ARCHIVE)
        if path.is_file() and path.name not in JUNK and str(relative) not in TRACKED:
            yield path, relative


def read_manifest():
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def index(origin):
    previous = {r["path"]: r for r in read_manifest()} if MANIFEST.exists() else {}
    rows = []
    for path, relative in archived_files():
        key = relative.as_posix()
        rows.append(
            {
                "path": key,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "origin": previous.get(key, {}).get("origin") or origin,
            }
        )
    with MANIFEST.open("w", newline="", encoding="utf-8") as handle:
        fields = ["path", "sha256", "bytes", "origin"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} files -> {MANIFEST.relative_to(ROOT)}")
    return 0


def verify():
    rows = read_manifest()
    listed = {r["path"] for r in rows}
    problems = []
    for row in rows:
        path = ARCHIVE / row["path"]
        if not path.is_file():
            problems.append(f"missing: {row['path']}")
        elif path.stat().st_size != int(row["bytes"]) or sha256(path) != row["sha256"]:
            problems.append(f"differs: {row['path']}")
    extra = [r.as_posix() for _, r in archived_files() if r.as_posix() not in listed]
    problems += [f"not in manifest: {p}" for p in extra]
    for problem in problems[:20]:
        print(problem)
    if problems:
        print(f"{len(problems)} problems in {len(rows)} manifest entries")
        return 1
    print(f"all {len(rows)} files verify against {MANIFEST.relative_to(ROOT)}")
    return 0


def pack():
    if verify():
        return 1
    out = ROOT / "dist" / "raw_archive"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    target = out / f"{ROOT.name}_raw_{stamp}.tar.gz"
    with tarfile.open(target, "w:gz") as tar:
        tar.add(MANIFEST, arcname="MANIFEST.csv")
        for path, relative in archived_files():
            tar.add(path, arcname=relative.as_posix())
    digest = sha256(target)
    (out / f"{target.name}.sha256").write_text(f"{digest}  {target.name}\n")
    print(f"{target.relative_to(ROOT)}  sha256 {digest}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("action", choices=["index", "verify", "pack"])
    parser.add_argument("--origin", default="", help="origin note for new entries")
    args = parser.parse_args()
    if args.action == "index":
        return index(args.origin)
    return verify() if args.action == "verify" else pack()


if __name__ == "__main__":
    sys.exit(main())

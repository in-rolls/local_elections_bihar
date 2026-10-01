"""Fetch source archives, rebuild geography, parse and verify published datasets."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

SPEC = Path(__file__).resolve().parents[1] / "data/PROVENANCE.json"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def selected_sources(spec, year, data):
    """Yield only the input groups declared for a production pipeline."""
    seen = set()
    for name in spec["pipelines"][year]["inputs"]:
        group = spec["source_groups"][name]
        root = data / group["root"]
        for pattern in group["include"]:
            paths = sorted(p for p in root.glob(pattern) if p.is_file())
            if not paths:
                raise FileNotFoundError(f"No sources match {root / pattern}")
            for path in paths:
                if path.name.startswith("._"):
                    continue
                relative = path.relative_to(data).as_posix()
                if relative not in seen:
                    seen.add(relative)
                    yield path, relative


def pack(spec, year, data, destination):
    """Create transport packaging; do not move or delete originals."""
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"bihar_{year}_sources.zip"
    if archive.exists():
        raise FileExistsError(archive)
    count = size = 0
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED) as output:
        for path, relative in selected_sources(spec, year, data):
            output.write(path, relative)
            count += 1
            size += path.stat().st_size
    return {
        "filename": archive.name,
        "url": None,
        "sha256": digest(archive),
        "bytes": archive.stat().st_size,
        "source_files": count,
        "source_bytes": size,
    }


def fetch(spec, year, data):
    archive = spec["archives"].get(year)
    if not archive or not archive.get("url"):
        raise ValueError(f"No published source archive for {year}; see PROVENANCE.json")
    data.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bihar-download-") as tmp:
        downloaded = Path(tmp) / "sources.zip"
        with (
            urlopen(archive["url"], timeout=120) as source,
            downloaded.open("wb") as out,
        ):
            shutil.copyfileobj(source, out)
        if (
            downloaded.stat().st_size != archive["bytes"]
            or digest(downloaded) != archive["sha256"]
        ):
            raise ValueError(
                "Source archive checksum or size differs; nothing extracted"
            )
        extract(downloaded, data, year)


def extract(archive, data, year):
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        names = set()
        for member in members:
            path = PurePosixPath(member.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in member.filename
                or path.parts[:2] != (year, "raw")
                or (member.external_attr >> 16) & 0o170000 == 0o120000
                or member.filename in names
            ):
                raise ValueError(
                    f"Unsafe or duplicate archive member: {member.filename}"
                )
            names.add(member.filename)
            target = data / member.filename
            if any(
                p.is_symlink() for p in [target, *target.parents] if p != data.parent
            ):
                raise ValueError(f"Extraction target contains a symlink: {target}")
            if target.exists():
                raise FileExistsError(
                    f"Refusing to overwrite existing source: {target}"
                )
        bad = source.testzip()
        if bad:
            raise ValueError(f"Corrupt source archive member: {bad}")
        source.extractall(data)


def frames(year, data, cache):
    if year == "2016":
        from scripts.year2016.collect import write_frame

        write_frame(data / "2016/raw/statewide", cache / "2016/frame.parquet")
    elif year == "2021":
        from scripts.shared.portal import enumerate_frame, read_saved
        from scripts.year2021 import (
            collect_byelections,
            collect_mukhiya,
            collect_offices,
        )

        raw = data / "2021/raw/statewide"
        output = cache / "2021"
        enumerate_frame(
            data / "2021/raw/portal_snapshot_2026",
            4,
            loader=read_saved,
            out=output / "frame.parquet",
        )
        collect_mukhiya.build_frame(
            raw, set(range(1, 39)), 4, loader=read_saved, frames=output
        )
        collect_offices.build_frame(raw, 4, loader=read_saved, frames=output)
        collect_byelections.build_frame(raw, 4, loader=read_saved, frames=output)


def parse(spec, year, data, cache):
    for step in spec["pipelines"][year]["steps"]:
        args = [a.format(data=data, cache=cache) for a in step["arguments"]]
        subprocess.run([sys.executable, "-m", step["module"], *args], check=True)


def verify(spec, year, data):
    for relative in spec["pipelines"][year]["manifests"]:
        path = data / relative
        manifest = json.loads(path.read_text())
        entries = manifest["files"]
        if isinstance(entries, list):
            entries = {item["path"]: item for item in entries}
        for name, info in entries.items():
            expected = info if isinstance(info, str) else info["sha256"]
            if digest(path.parent / name) != expected:
                raise ValueError(f"Output checksum differs: {path.parent / name}")
    if year in {"2016", "2021"}:
        subprocess.run(
            [
                sys.executable,
                "-m",
                f"scripts.year{year}.parse",
                "--check",
                "--out",
                str(data / year),
            ],
            check=True,
        )
    print(f"Verified {year} published files")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["fetch", "parse", "verify", "frames", "pack"]
    )
    parser.add_argument(
        "--year", choices=["2011", "2016", "2021", "all"], required=True
    )
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--cache", type=Path, default=Path(".cache"))
    parser.add_argument("--destination", type=Path, default=Path(".cache/archives"))
    args = parser.parse_args()
    spec = json.loads(SPEC.read_text())
    years = list(spec["pipelines"]) if args.year == "all" else [args.year]
    for year in years:
        if args.action == "pack":
            spec["archives"][year] = pack(spec, year, args.data, args.destination)
            SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
        elif args.action == "frames":
            frames(year, args.data, args.cache)
        elif args.action == "parse":
            parse(spec, year, args.data, args.cache)
        else:
            globals()[args.action](spec, year, args.data)


if __name__ == "__main__":
    main()

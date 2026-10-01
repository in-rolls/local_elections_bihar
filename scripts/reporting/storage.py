"""Measure the current source and working directories without reading file contents."""

import os
from pathlib import Path

SOURCE_YEARS = ("2006", "2011", "2016", "2021", "undated")


def file_sizes(path):
    if path.is_symlink():
        raise ValueError(f"Unexpected link inside source collection: {path}")
    if path.is_file():
        yield path, path.stat().st_size
        return
    with os.scandir(path) as entries:
        for entry in entries:
            if entry.name == ".DS_Store" or entry.name.startswith("._"):
                continue
            child = Path(entry.path)
            if entry.is_symlink():
                raise ValueError(f"Unexpected link inside source collection: {child}")
            if entry.is_dir(follow_symlinks=False):
                yield from file_sizes(child)
            elif entry.is_file(follow_symlinks=False):
                yield child, entry.stat(follow_symlinks=False).st_size
            else:
                raise ValueError(f"Unexpected filesystem entry: {child}")


def asset_summary(data):
    """Require the complete collection so an unmounted drive cannot look empty."""
    rows = []
    for year in SOURCE_YEARS:
        for role in ("raw", "interim"):
            root = data / year / role
            if role == "interim" and not root.exists() and not root.is_symlink():
                continue
            if not root.is_dir():
                raise ValueError(f"Storage unavailable: {root}; mount the source drive")
            for path in sorted(root.iterdir()):
                if path.name == ".DS_Store" or path.name.startswith("._"):
                    continue
                files, size, formats = 0, 0, set()
                for child, byte_count in file_sizes(path):
                    files += 1
                    size += byte_count
                    extension = next(
                        (
                            ext
                            for ext in (".jsonl.gz", ".html.gz", ".tar.gz")
                            if child.name.endswith(ext)
                        ),
                        child.suffix or "no extension",
                    )
                    formats.add(extension)
                rows.append(
                    {
                        "path": path.relative_to(data).as_posix(),
                        "files": files,
                        "bytes": size,
                        "formats": sorted(formats),
                    }
                )
    return rows

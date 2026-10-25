"""Write and verify a release folder: validated Parquet plus MANIFEST.json."""

import hashlib
import json

import polars as pl

from local_elections_bihar.paths import ROOT
from local_elections_bihar.shared.schema import dictionary_rows, polars_schema

PACKAGE = ROOT / "src" / "local_elections_bihar"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(out, tables, models, code, **meta):
    """tables: {name: list of row dicts}; models: {name: pandera model}."""
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for name, model in models.items():
        frame = model.validate(
            pl.DataFrame(tables[name], schema=polars_schema(model), orient="row"),
            lazy=True,
        )
        path = out / f"{name}.parquet"
        frame.write_parquet(path, compression="zstd", statistics=True)
        files.append(
            {
                "path": path.name,
                "rows": frame.height,
                "sha256": digest(path),
                "columns": {
                    r["column"]: {
                        k: v for k, v in r.items() if k not in {"table", "column"}
                    }
                    for r in dictionary_rows(name, model)
                },
            }
        )
    manifest = {
        **meta,
        "files": files,
        "code_sha256": {name: digest(PACKAGE / name) for name in code},
    }
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def verify(out, models):
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    for info in manifest["files"]:
        path = out / info["path"]
        if digest(path) != info["sha256"]:
            raise SystemExit(f"checksum differs from manifest: {path}")
        frame = models[path.stem].validate(pl.read_parquet(path), lazy=True)
        if frame.height != info["rows"]:
            raise SystemExit(f"row count differs from manifest: {path}")
    print(
        json.dumps(
            {"verified": str(out.relative_to(ROOT)), "files": len(manifest["files"])}
        )
    )

#!/bin/sh
set -eu
if command -v caffeinate >/dev/null 2>&1 && [ "${BIHAR_AWAKE:-0}" != 1 ]; then
    exec env BIHAR_AWAKE=1 caffeinate -dims "$0" "$@"
fi
if [ ! -f data/raw/statewide_2021/frame.parquet ]; then
    (cd data/raw && shasum -a 256 -c CHECKSUMS)
    mkdir -p data/raw/statewide_2021
    tar -xzf data/raw/statewide_2021.tar.gz -C data/raw/statewide_2021
fi
uv run python scripts/sec_2021.py fetch --raw data/raw/statewide_2021 --districts $(seq 1 38)
uv run python scripts/release_2021.py
uv run python scripts/affidavits.py frame --source data/interim/2021/parsed/mukhiya_2021.parquet --frame data/interim/2021/affidavit_frame.parquet
uv run python scripts/affidavits.py download --frame data/interim/2021/affidavit_frame.parquet

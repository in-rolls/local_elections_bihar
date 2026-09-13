#!/bin/sh
# 2021 ward member, panch, sarpanch, samiti and zila parishad records.
# Resumable: completed requests are reused, so rerun after any interruption.
set -eu
if command -v caffeinate >/dev/null 2>&1 && [ "${BIHAR_AWAKE:-0}" != 1 ]; then
    exec env BIHAR_AWAKE=1 caffeinate -dims "$0" "$@"
fi
if [ ! -f data/raw/statewide_2021/2021/frame.parquet ]; then
    (cd data/raw && shasum -a 256 -c CHECKSUMS)
    mkdir -p data/raw/statewide_2021
    tar -xzf data/raw/statewide_2021.tar.gz -C data/raw/statewide_2021
fi

# A pass that leaves failed units exits non-zero; later passes retry only those.
passes() {
    for pass in 1 2 3 4 5; do
        if uv run python scripts/offices_2021.py "$@"; then
            return 0
        fi
        echo "pass $pass of '$*' left failures; retrying in 10 minutes" >&2
        sleep 600
    done
    return 1
}
[ -f data/raw/statewide_2021/2021/offices/frame.parquet ] || passes frame
passes current
passes dated --posts 4 5 6
passes dated --posts 1 2
uv run python scripts/offices_2021.py parse
uv run python scripts/audit_offices_2021.py

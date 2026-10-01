#!/bin/sh
# 2021: every office, the by-elections and the current-term feeds, then the
# release and its audit. Affidavit acquisition is a separate explicit step.
# Resumable: completed requests are reused, so rerun after any interruption.
set -eu
if command -v caffeinate >/dev/null 2>&1 && [ "${BIHAR_AWAKE:-0}" != 1 ]; then
    exec env BIHAR_AWAKE=1 caffeinate -dims "$0" "$@"
fi
if [ ! -f data/2021/raw/statewide/frame.parquet ]; then
    uv run python scripts/sec_portal.py list --raw data/2021/raw/statewide
fi

uv run python scripts/sec_2021.py fetch --raw data/2021/raw/statewide --districts $(seq 1 38)

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
[ -f data/2021/raw/statewide/2021/offices/frame.parquet ] || passes frame
passes current
passes dated --posts 4 5 6
passes dated --posts 1 2
[ -f data/2021/raw/statewide/byelections/frame.parquet ] ||
    uv run python scripts/byelections_2021.py frame
for pass in 1 2 3 4 5; do
    uv run python scripts/byelections_2021.py fetch && break
    echo "pass $pass of by-election fetch left failures; retrying in 10 minutes" >&2
    sleep 600
done

uv run python scripts/build_2021.py
uv run python scripts/audit_2021.py
uv run python scripts/check_reservations_2021.py

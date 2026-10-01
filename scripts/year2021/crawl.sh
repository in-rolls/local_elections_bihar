#!/bin/sh
# 2021: every office, the by-elections and the current-term feeds, then the
# release and its audit. Affidavit acquisition is a separate explicit step.
# Resumable: completed requests are reused, so rerun after any interruption.
set -eu
if command -v caffeinate >/dev/null 2>&1 && [ "${BIHAR_AWAKE:-0}" != 1 ]; then
    exec env BIHAR_AWAKE=1 caffeinate -dims "$0" "$@"
fi
if [ ! -f data/2021/raw/statewide/frame.parquet ]; then
    uv run python -m scripts.shared.portal list --raw data/2021/raw/statewide
fi

uv run python -m scripts.year2021.collect_mukhiya fetch --raw data/2021/raw/statewide --districts $(seq 1 38)

# A pass that leaves failed units exits non-zero; later passes retry only those.
passes() {
    for pass in 1 2 3 4 5; do
        if uv run python -m scripts.year2021.collect_offices "$@"; then
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
    uv run python -m scripts.year2021.collect_byelections frame
for pass in 1 2 3 4 5; do
    uv run python -m scripts.year2021.collect_byelections fetch && break
    echo "pass $pass of by-election fetch left failures; retrying in 10 minutes" >&2
    sleep 600
done

uv run python -m scripts.year2021.parse
uv run python -m scripts.year2021.audit
uv run python -m scripts.year2021.reservation_check

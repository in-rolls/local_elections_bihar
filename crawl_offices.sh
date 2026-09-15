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

# Reading ~560k small files in crawl order is slow on a spinning disk; pack each
# feed once, in directory order, and build from the archives.
archive=data/interim/2021/archive
mkdir -p "$archive"
for feed in 2021/offices/frame 2021/offices/p1 2021/offices/p2 2021/offices/p4 \
    2021/offices/p5 2021/offices/p6 current/winners current/reservations; do
    name=$(echo "$feed" | tr / _)
    COPYFILE_DISABLE=1 tar -cf "$archive/$name.tar.part" -C data/raw/statewide_2021 "$feed"
    mv "$archive/$name.tar.part" "$archive/$name.tar"
done
cp data/raw/statewide_2021/2021/offices/frame.parquet "$archive/offices_frame.parquet"
uv run python scripts/build_2021.py
uv run python scripts/audit_2021.py

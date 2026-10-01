#!/bin/sh
# Re-collect the 2016 results form: frame of every unit, then each unit's table.
# Resumable: finished units are reused, so rerun after any interruption.
set -eu
if command -v caffeinate >/dev/null 2>&1 && [ "${BIHAR_AWAKE:-0}" != 1 ]; then
    exec env BIHAR_AWAKE=1 caffeinate -dims "$0" "$@"
fi
passes() {
    for pass in 1 2 3 4 5; do
        if uv run python scripts/sec_2016.py "$@" --workers 2; then
            return 0
        fi
        echo "pass $pass of '$*' left failures; retrying in 10 minutes" >&2
        sleep 600
    done
    return 1
}
passes frame
passes results

# Build offline from one tar of the ledgers (2,705 small files read slowly from
# the staging disk), then compare the release with independent sources.
make archive-2016
uv run python scripts/roster_2016.py parse
make build-2016
make audit-2016

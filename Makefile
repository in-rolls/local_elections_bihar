.PHONY: check test verify verify-2016 verify-2021 build-2016 \
	audit-2016 build-2021 audit-2021 reservation-check-2021 data-verify data-summary parse-2011 coverage

check:
	uv sync --frozen --group dev
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q

test:
	uv run pytest -q

verify: verify-2016 verify-2021

verify-2016:
	uv run python scripts/build_2016.py --check

verify-2021:
	uv run python scripts/build_2021.py --check

build-2016:
	uv run python scripts/build_2016.py

audit-2016:
	uv run python scripts/roster_2016.py parse
	uv run python scripts/audit_2016.py

build-2021:
	uv run python scripts/build_2021.py

audit-2021:
	uv run python scripts/audit_2021.py

reservation-check-2021:
	uv run python scripts/check_reservations_2021.py

data-verify:
	uv run python scripts/data_inventory.py verify

data-summary:
	uv run python scripts/data_inventory.py summary

parse-2011:
	uv run python scripts/parse_2011.py
	uv run python scripts/parse_2011_reports.py

coverage:
	uv run python scripts/election_coverage.py

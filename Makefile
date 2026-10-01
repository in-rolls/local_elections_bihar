.PHONY: check test verify verify-2016 verify-2021 build-2016 \
	audit-2016 build-2021 audit-2021 reservation-check-2021 data-summary parse-2011

check:
	uv sync --frozen --group dev
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q

test:
	uv run pytest -q

verify: verify-2016 verify-2021

verify-2016:
	uv run python -m scripts.year2016.parse --check

verify-2021:
	uv run python -m scripts.year2021.parse --check

build-2016:
	uv run python -m scripts.year2016.parse

audit-2016:
	uv run python -m scripts.year2016.rosters parse
	uv run python -m scripts.year2016.audit

build-2021:
	uv run python -m scripts.year2021.parse

audit-2021:
	uv run python -m scripts.year2021.audit

reservation-check-2021:
	uv run python -m scripts.year2021.reservation_check

data-summary:
	uv run python -m scripts.reporting.summary

parse-2011:
	uv run python -m scripts.year2011.parse_gaya
	uv run python -m scripts.year2011.parse_reports

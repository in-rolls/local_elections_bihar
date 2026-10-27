.PHONY: fetch-sources parse check test verify verify-2016 verify-2021 build-2016 \
	audit-2016 build-2021 audit-2021 reservation-check-2021 data-summary parse-2011 \
	linkage verify-linkage winner-list-2016 verify-winner-list-2016 \
	collect-wayback parse-2006 verify-2006 parse-2001 verify-2001

check:
	uv sync --frozen --group dev
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q
	uv run python -m local_elections_bihar.build.fetch_log --check
	uv run python -m local_elections_bihar.parse.release_2006 --check
	uv run python -m local_elections_bihar.parse.mukhiya_2001 --check
	uv run python -m local_elections_bihar.build.profile_year_check

test:
	uv run pytest -q

YEAR ?= all

fetch-sources:
	uv run python -m local_elections_bihar.sources fetch --year $(YEAR)

parse:
	uv run python -m local_elections_bihar.sources parse --year $(YEAR)

verify:
	uv run python -m local_elections_bihar.sources verify --year $(YEAR)

verify-2016:
	uv run python -m local_elections_bihar.year2016.parse --check

verify-2021:
	uv run python -m local_elections_bihar.year2021.parse --check

build-2016:
	uv run python -m local_elections_bihar.sources parse --year 2016

audit-2016:
	uv run python -m local_elections_bihar.year2016.rosters parse
	uv run python -m local_elections_bihar.year2016.audit

build-2021:
	uv run python -m local_elections_bihar.sources parse --year 2021

audit-2021:
	uv run python -m local_elections_bihar.year2021.audit

reservation-check-2021:
	uv run python -m local_elections_bihar.year2021.reservation_check

data-summary:
	uv run python -m local_elections_bihar.reporting.summary

parse-2011:
	uv run python -m local_elections_bihar.sources parse --year 2011

linkage:
	uv run python -m local_elections_bihar.linkage.mukhiya build

verify-linkage:
	uv run python -m local_elections_bihar.linkage.mukhiya check

winner-list-2016:
	uv run python -m local_elections_bihar.year2016.winner_list

verify-winner-list-2016:
	uv run python -m local_elections_bihar.year2016.winner_list --check

# old SEC and district sites from the Wayback Machine: 2001 winner lists, the
# 2006 reservation directive, Madhubani's 2006 result notices (network)
collect-wayback:
	uv run python -m local_elections_bihar.collect.wayback

# 2006 SEC workbooks: member seats with reservation, mukhiya and sarpanch winners
parse-2006:
	uv run python -m local_elections_bihar.parse.release_2006

verify-2006:
	uv run python -m local_elections_bihar.parse.release_2006 --check

# 2001 mukhiya winners from the SEC site's division lists (Akruti)
parse-2001:
	uv run python -m local_elections_bihar.parse.mukhiya_2001

verify-2001:
	uv run python -m local_elections_bihar.parse.mukhiya_2001 --check

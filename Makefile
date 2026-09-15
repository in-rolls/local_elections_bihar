.PHONY: check test to-parquet verify-data ci-docker release-data verify-2021 \
	build-2021 verify-2021-panchayat audit-2021

check:
	uv sync --frozen --group dev
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q
	uv run pre-commit run --all-files
	$(MAKE) verify-data
	$(MAKE) verify-2021
	$(MAKE) verify-2021-panchayat

test:
	uv run pytest -q

to-parquet:
	uv run python scripts/to_parquet.py

verify-data:
	uv run python scripts/to_parquet.py --check

ci-docker:
	@for version in 3.12 3.14; do \
	  COPYFILE_DISABLE=1 tar --exclude=._* --exclude=__pycache__ --exclude=.DS_Store --exclude=.git --exclude=.venv --exclude=.ruff_cache --exclude=.pytest_cache --exclude=data/derived -cf - . | \
	  docker run --rm -i python:$$version-slim sh -ec 'mkdir /work; tar -xf - -C /work; cd /work; pip install -q uv; uv sync --frozen --group dev; uv run ruff check .; uv run ruff format --check .; uv run pytest -q; uv run python scripts/to_parquet.py --check' || exit $$?; \
	done

release-data:
	uv run python scripts/release_2021.py

verify-2021:
	uv run python scripts/release_2021.py --check

build-2021:
	uv run python scripts/build_2021.py

verify-2021-panchayat:
	uv run python scripts/build_2021.py --check

audit-2021:
	uv run python scripts/audit_2021.py

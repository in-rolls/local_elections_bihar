.PHONY: check test to-parquet verify-data ci-docker

check:
	uv sync --frozen --group dev
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q
	uv run pre-commit run --all-files
	$(MAKE) verify-data

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

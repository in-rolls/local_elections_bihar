.PHONY: check test verify verify-2016 verify-2021 ci-docker archive-2016 build-2016 \
	audit-2016 build-2021 audit-2021 reservation-check-2021 raw-verify raw-archive

check:
	uv sync --frozen --group dev
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q
	uv run pre-commit run --all-files
	$(MAKE) verify

test:
	uv run pytest -q

verify: verify-2016 verify-2021

verify-2016:
	uv run python scripts/build_2016.py --check

verify-2021:
	uv run python scripts/build_2021.py --check

ci-docker:
	@for version in 3.12 3.14; do \
	  COPYFILE_DISABLE=1 tar --exclude=._* --exclude=__pycache__ --exclude=.DS_Store --exclude=.git --exclude=.venv --exclude=.ruff_cache --exclude=.pytest_cache --exclude=data/derived --exclude=data/interim -cf - . | \
	  docker run --rm -i python:$$version-slim sh -ec 'mkdir /work; tar -xf - -C /work; cd /work; pip install -q uv; uv sync --frozen --group dev; uv run ruff check .; uv run ruff format --check .; uv run pytest -q; uv run python scripts/build_2016.py --check; uv run python scripts/build_2021.py --check' || exit $$?; \
	done

# One tar in directory order: the build reads it far faster than 2,705 small files.
archive-2016:
	mkdir -p data/interim/2016/archive
	COPYFILE_DISABLE=1 tar -cf data/interim/2016/archive/2016_results.tar.part \
	  -C data/raw/statewide_2016 2016/results
	mv data/interim/2016/archive/2016_results.tar.part data/interim/2016/archive/2016_results.tar

build-2016:
	uv run python scripts/build_2016.py

audit-2016:
	uv run python scripts/audit_2016.py

build-2021:
	uv run python scripts/build_2021.py

audit-2021:
	uv run python scripts/audit_2021.py

reservation-check-2021:
	uv run python scripts/check_reservations_2021.py

raw-verify:
	python3 scripts/raw_archive.py verify

raw-archive:
	python3 scripts/raw_archive.py pack $(if $(OUT),--out $(OUT),)

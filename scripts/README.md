# Scripts

Run commands from the repository root. Python entry points use `uv run python -m`;
no package installation or custom import path is needed. `make` provides the
usual parsing, validation and summary commands.

| Directory | Responsibility | Main entry points |
| --- | --- | --- |
| `year2011/` | Parse historical reports and workbooks; reviewed Hindi character maps stay beside the parser | `parse_gaya`, `parse_reports`; `make parse-2011` |
| `year2016/` | Collect the archived SEC form, parse its responses and compare sources | `collect`, `parse`, `rosters`, `audit`; `make build-2016`, `make verify-2016` |
| `year2021/` | Collect general-election and by-election responses, parse them and compare reservation sources | `collect_mukhiya`, `collect_offices`, `collect_byelections`, `parse`, `audit`, `reservation_check` |
| `shared/` | HTTP/request-ledger handling, name matching and common schema helpers | Imported by the election modules; `portal` also enumerates the 2021 seat frame |
| `reporting/` | Produce the single data-guide table from published records and current storage sizes | `make data-summary` |
| `affidavits/` | Existing affidavit tools; outside current collection priorities | `pipeline`; run only for explicitly requested affidavit work |

For example, `uv run python -m scripts.year2016.collect --help` lists collection
options. The `crawl.sh` files orchestrate live collection and subsequent parsing;
they are explicit collection jobs, not checks to run during ordinary maintenance.
The data summary measures the full mounted source tree and can take several
minutes; it is not run by tests or CI.

Original sources remain under `data/<year>/raw`. The 2016 reservation audit's
regenerable table goes under ignored `.cache/`. Published column definitions,
source/output hashes and audit findings live in one `MANIFEST.json` per dataset.
Historical manifests retain hashes of the code that produced their tables;
those hashes do not assert that today's reorganized scripts are byte-identical.

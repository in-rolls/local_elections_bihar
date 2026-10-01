# Working on this repository

- This is a data collection and parsing repository, not a distributable software
  package. Do not apply preen or add package-release infrastructure unless asked.
- Focus on collecting and parsing seat reservations, candidates and winners.
  Keep source receipts and preserve uncertainty without inventing classifications.
- Use the existing local environment. Do not start Docker or another VM for
  routine work. Container checks require an explicit request or a demonstrated
  container-specific failure.
- Match validation to the change. Run affected tests during code edits and
  `make check` once before a code PR. Documentation-only edits need diff review.
- Run `make verify` locally when published tables or their validation code change.
  Do not rebuild datasets, rescan the raw archive or repeat successful checks
  unless a new change or failure makes that necessary.
- GitHub CI supplies one Python 3.14 check on the PR. Do not add a local version
  matrix or wait for a second run after merging. Do not add pre-commit as another
  layer over the same lint and formatting checks.
- Use the existing parsers and standard tools. Add infrastructure only to solve
  a concrete problem; avoid duplicate data copies and disposable artifacts in Git.
- Check official documentation when an API question arises. Install missing
  test dependencies when needed rather than silently skipping relevant tests.

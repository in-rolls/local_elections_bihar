# Existing affidavit work


Affidavits are outside the current collection scope. Existing files and their
receipts are retained separately; the general collection scripts do not run
this workflow.

<details>
<summary>Existing Arwal transcription and optional affidavit commands</summary>

[`data/2021/affidavits/`](./) holds a different kind of record from the rest of `data/2021`. The tables above come from the SEC's structured feeds: one row per candidate or result, the same fields everywhere. An affidavit is the nomination paper a candidate files: a scanned PDF of sworn self-declarations, including education, prior office and seat reservation, in whatever layout and handwriting the candidate used. The candidate list links each candidate's PDF (`affidavit_url`), but its contents exist only as page images, so every value here was read off a page and carries the PDF hash and page number it came from. Nothing in it was checked against another source.

**Education has been transcribed for 64 Arwal winners.** All 64 winners were linked to candidate lists using district, block, panchayat and candidate serial, then their downloaded nomination PDFs were inspected. [The export](education.csv) retains the reported qualification, degree and literacy indicators, prior elected office, document reservation text, source URL, page number and PDF hash. [Inspected pages](education_pages) accompany the transcriptions.

Degree status is unresolved for seven winners: two documents lack the candidate's education page, one names a school without a qualification, one says only "EDUCATED," and three have ambiguous qualification text. Unknowns remain null. Reservation is classified from document text for 51 winners; 13 remain unspecified. Of the 25 document-classified women's reserved seats, 21 have classified degree status; the corresponding counts are 24 of 26 open seats and 12 of 13 seats with unspecified reservation. These are extraction counts, not reservation-effect estimates. [Coverage and provenance](education.json).

Codex visually transcribed these records; there has been no independent second coding. Tesseract locates likely pages but does not assign qualifications. Candidate and proposer biographies are distinguished. Qualifications are self-reported, and a blank field is not evidence of illiteracy. Statewide affidavit collection and extraction were stopped at the owner's request. The public winner table and 2021 candidate-detail page checked for Awgila contain no structured education field; statewide 2021 education remains unavailable.

<details>
<summary>Inspect a qualification declaration</summary>

Rajanti Devi's candidate biography reports "इंटर पास" (intermediate passed). The seat-reservation field reads "सामान्य महिला." [Original PDF, page 12](https://sec2021.bihar.gov.in/ForPublicPDF_P/Documents1n2/NominationDoc/20210909141417391.pdf#page=12).

<img src="education_pages/33_1_330010011_4_p12.png" alt="Candidate biography showing the education and seat-reservation fields" width="500">

</details>

Affidavit work is deferred. These commands are a separate optional pipeline. Install Poppler (`pdfinfo`, `pdftoppm`, `pdftotext`) and Tesseract with English and Hindi language data before running it (`brew install poppler tesseract tesseract-lang` on macOS; `poppler-utils tesseract-ocr tesseract-ocr-hin` on Ubuntu):

```sh
uv run python -m scripts.affidavits.pipeline frame
caffeinate -dims uv run python -m scripts.affidavits.pipeline download
caffeinate -dims uv run python -m scripts.affidavits.pipeline locate
uv run python -m scripts.affidavits.pipeline export
```

Already-collected PDFs and download receipts are in `data/2021/raw/affidavits/`; page-location text, images and caches are in `data/2021/interim/affidavits/`. Further acquisition and extraction are deferred; the general crawl does not run them. PDFs are checked for a PDF signature, readable page count and SHA-256; failures are retained and retried on resume, and the download stops before consuming the final 5 GiB of disk space. Export combines the checked-in review CSV with downloaded document metadata and page images. It rejects duplicate or missing review keys, invalid binary codes, mismatched source hashes, and pages outside the document. The review CSV is the visual-transcription input; OCR alone cannot regenerate it. `graduate_plus=1` means a reported completed degree, `0` a reported lower qualification, and null an unresolved level. `illiterate` and `prior_elected` likewise preserve unknowns. `quota_document` records women's seat reservation from the document, independently of candidate gender; it is not an official reservation-roll validation.

</details>

### Collection and rebuild

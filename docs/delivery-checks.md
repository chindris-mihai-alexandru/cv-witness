# Checked local CV exports

Date: 2026-10-09
POC: Mihai-Alexandru Chindriș
TL;DR: Render approved, self-contained HTML to a temporary PDF, run the shared checks, then publish only a passing candidate. A selected posting triggers phrase review automatically.

## Tools and inputs

Use Python 3.11+, a Chromium-family browser and Poppler (`pdfinfo`, `pdftotext`). Linux and macOS are covered by CI. `pdftoppm` is also needed to reproduce the fictional website sample.

The renderer discovers macOS browser applications and common Linux executable names. Set `CV_WITNESS_BROWSER` or pass `--browser` for a different executable. An explicit invalid setting fails instead of silently falling back.

Render only approved, self-contained HTML with one `@page` rule and an explicit size declaration. Scripts, embedded documents and resource-loading attributes/styles are rejected, including CSS resource tokens written with escapes. This preflight supports the bundled templates; it is not a general-purpose hostile-HTML sandbox. Review the HTML yourself and use trusted source files.

## Check a posting before tailoring

For a job supplied as a URL, check the listing before spending time tailoring:

```sh
python3 scripts/check_posting_liveness.py 'https://jobs.example.com/role' \
  --expect "Application Support Engineer"
```

The script reports `dead` for HTTP 404/410 or a closure phrase on a non-200 response. A closure phrase on a 200 page, a missing expected title, an unexpected redirect or a network error is `suspicious`; verify it in a browser before treating it as live or closed. A `live` result is only a basic HTTP/content check. The script does not render JavaScript and does not fetch or store the candidate's CV.

## Render and check before publication

```sh
sh render.sh approved.html "$HOME/Downloads/Candidate-CV-Company-Role.pdf" a4 \
  --posting selected-posting.txt \
  --expected-text "Professional Experience"
```

The default page limit is one. Choose `letter` explicitly for US Letter and use `--max-pages 2` when two pages have been approved. The same content may occupy different page counts on A4 and Letter. A failing page limit is reported; text is never dropped or silently reduced to make a pass.

`--posting` selects a local `.txt` or `.md` file. Its presence triggers the shared phrase checker; the default policy fails on a literal run of four or more shared words. Common industry wording can match, so inspect the wording privately. Use `--overlap-policy review` only after deciding that these matches should be reviewed rather than blocked. Do not add false distinctions to accurate technical names merely to evade the detector.

The renderer uses a fresh temporary browser profile and a percent-encoded local file URL. The source is unchanged. Temporary HTML/PDF/profile files are removed when the render completes or fails.

A passing PDF is published atomically with owner-only file permissions. An existing output is preserved unless `--replace` is explicitly requested. Even with `--replace`, a failed render or validation cannot replace the previous PDF. Symlinked output paths and directories are rejected; use a canonical destination.

## Preserve an approved design

Before tailoring, choose the latest candidate-approved CV as the visual baseline, or ask which reference/template is approved. Keep its section order and visual hierarchy by default across Quick and local authoring. Present redesigns or section-order changes as optional choices and get approval first. If there is no readable baseline, state that clearly and ask before selecting a default. Compare exported pages with the reference; report any differences or unverified details.

## Check a PDF from another authoring tool

```sh
python3 scripts/check_cv.py exported.pdf \
  --paper a4 --max-pages 1 \
  --expected-text "Alex Morgan" \
  --ordered-text "Professional Summary" \
  --ordered-text "Skills" \
  --ordered-text "Professional Experience" \
  --strict-ordered-text \
  --posting selected-posting.txt
```

The report checks:

- A readable PDF signature and bounded file size.
- Every page's A4/Letter geometry and the chosen page limit.
- Live extracted text on every page, encryption, unresolved fill/template markers and replacement glyphs.
- Expected text supplied by the caller. Failure reports use item numbers rather than printing private claims.
- Optional `--ordered-text` landmarks, checked in the sequence supplied; reports never echo the private text.
- Posting phrase overlap when a posting is selected.

Use `--expected-text` for the candidate's name and details that must survive export. Use repeated `--ordered-text` flags for important section headings in the approved order. Add `--strict-ordered-text` when each heading should match a standalone extracted line; this catches body-text mentions that could otherwise satisfy the landmark. The check still does not establish complete reading order or field-level ATS parsing. Compare the export visually with the latest candidate-approved CV, preserve its design unless a change was approved, and inspect each page for wrapping or clipping. Verify facts against the selected sources. If an application offers resume autofill, review and correct the fields before submitting.

## Number fact gate

After PDF checks, run the number gate against the private, approved fact sources:

```sh
python3 scripts/check_cv_numbers.py exported.pdf \
  --source foundation.md --source provenance.md
```

Repeat `--source` for any approved per-application evidence file. The gate flags numeric claims it cannot find in any selected source, normalizing grouping commas and respecting digit boundaries. It intentionally skips years from 1900 to 2099, single-digit values and numbers embedded in alphanumeric identifiers. This is a lexical safeguard, not a fact checker: a matching number can still be used in the wrong context, and skipped values still need human review. Keep source files private and out of logs or public artifacts.

## Phrase diagnostics

```sh
python3 scripts/jd_overlap.py CV.pdf selected-posting.txt --strict --json
```

Reports contain shared-run counts, maximum length and word offsets in both documents. Maximal runs are reported instead of repeatedly listing the smaller pieces of a longer match. Case, punctuation and diacritics are normalized; Unicode letters are retained.

Passages are omitted by default. `--show-phrases` explicitly allows shared wording in the standalone check report; do not use it in public logs with real documents. All checks are local and make no model or account calls.

Exit codes are consistent: **0** passes the selected policy, **1** reports failed checks, and **2** reports an invalid input, missing tool or local operation failure. A non-strict phrase report can contain matches and return 0 because it asks for review. A pass does not establish originality, successful parsing by a particular ATS, or ATS compatibility. For example, Greenhouse documents file-size and format-related parse failures, and Workday describes parsing as a configured process whose output recruiters review. Use the employer's accepted file type, inspect extracted text and section landmarks, and correct any employer autofill fields before submission.

## Public CI and failure cases

The required test workflow runs on every PR and main push. It uses only fictional documents and temporary outputs. Actual Chromium/Poppler tests must run in CI; missing tools cause failure rather than a skipped green job.

Tests include A4/Letter geometry, Unicode extraction, strict posting failures, expected-text failures, unresolved markers, extra/blank pages, output preservation and a shell invocation from another directory. Tool output and runtime are bounded, with private tool diagnostics discarded.

`--no-sandbox` is available only with `CI=true` for an already isolated runner/container. It is not a recommended local flag or a claim that an environment is isolated merely because a variable is set.

Run locally:

```sh
CV_WITNESS_REQUIRE_PDF_TESTS=1 PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s tests -q
```

Without the require flag, local environments missing browser/PDF tools skip the real-export tests and must not claim to have verified rendering. Corpus and unit tests still run.

The website sample remains fictional. `python3 scripts/render_sample.py --output-dir /canonical/temporary/path` reproduces it without changing the published assets; the helper uses the same checked renderer.

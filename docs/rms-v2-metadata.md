# Resume Metadata Standard v2 (RMS)

Rezi's `rezi-io/resume-standard` repo defines an XMP metadata layer for PDFs.
It is not a CV layout template and it is not an ATS integration.

## What is actually upstream

Checked 2026-11-24:

- Last code commit: `7dfe5c3`, 2025-03-21. No releases published.
- The only implementation artifacts are `parser/src/parser.cpp`, three example
  PDFs and `resume-builder/.ExifTool_config`.
- No declarative template file exists. The full v2 key vocabulary is the
  ExifTool config: 1,274 keys across contact, summary, ten indexed sections
  (indices 0-15), and section counts.
- No newer RMS version was found online in the changelog, docs or GitHub.
- Rezi's 2026 blog posts still describe the same v2 standard. The demo site
  `resume-metadata-standard.com` only offers a parser.

`rms_v2.0.1` is therefore the current version to write. A parser accepts a PDF
when the `pdf:Producer` field starts with `rms_v2`.

## What it can and cannot do

- It can give an RMS-aware reader an exact, structured copy of CV fields.
- It cannot make a non-RMS ATS read those fields. No major ATS vendor is
  documented as consuming RMS.
- Rezi's own Workday test lost a large share of resume data even from its own
  templates. Its "100% accuracy" wording means faithful copying by an RMS
  parser, not certainty of ATS parsing, ranking or interviews.

Use it as an invisible, final, optional layer on top of the approved CV layout.

## Generate the template

```sh
python3 scripts/rms_metadata.py --print-template
```

This prints the synthetic 1,274-key template generated from the vocabulary in
the script. Values are `n/a` placeholders; counts are `0`. The script is the
single source of truth, so no static duplicate is committed.

## Attach metadata

From canonical CV fields:

```sh
python3 scripts/rms_metadata.py --pdf CV.pdf --fields fields.json --output CV-rms.pdf
```

From an explicit RMS key/value JSON object:

```sh
python3 scripts/rms_metadata.py --pdf CV.pdf --metadata rms.json --output CV-rms.pdf
```

Use `--in-place` instead of `--output` to replace the input atomically.

The writer validates keys, count/index bounds, timestamps, booleans and date
formats before writing. It checks that the original PDF bytes are preserved,
that the new startxref points at the appended xref section, and that the XMP
round-trips. It rejects encrypted PDFs, xref-stream PDFs and inputs that
already contain XMP; re-render from the source rather than stacking updates.

Verify:

```sh
python3 scripts/rms_metadata.py --pdf CV-rms.pdf --verify
```

Verification prints producer and counts only, never contact details. The
writer appends a PDF incremental update, so the original page bytes stay
untouched. Reject xref-stream PDFs instead of trying to rewrite them.

The optional upstream C++ parser can also be built from the stale repo and run
against the output; cv-witness does not depend on it.

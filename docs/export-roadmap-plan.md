# Checked exports and template variants

Date: 2026-10-09
POC: cv-witness contributors
TL;DR: Finish pre-delivery checks (#5) before variable templates (#4), then publish interactive maps of the verified workflow. Keep all development and CI inputs fictional.

## Order of work

1. Harden selected Markdown imports for Obsidian comments, embeds, callouts and author properties. Never resolve vault links or scan a personal vault.
2. Implement one reusable export validator: unresolved markers, live text, expected text, page count/geometry, and automatic posting-overlap review. Keep factual review and visual inspection explicit.
3. Repair the renderer's paper override, temporary files, browser discovery and atomic output handling. Reuse the validator for the public sample and CI.
4. Close #5 only after positive and deliberately failing synthetic cases pass locally and in CI.
5. Add a structured CV input with repeatable roles and optional sections. Engineering, Operations/Support, Research and Management are presets over one layout, not four copied renderers. Support A4 and Letter, with explicit page limits.
6. Exercise every lane/paper combination and long content, empty optional sections, Unicode and invalid data. Never hide content or reduce text below a legibility floor to claim a one-page pass.
7. Close #4 after the shared checks and real rendered outputs pass.
8. Produce one concise animated workflow and a separate interactive source map using the installed diagram generators. Scan only a sanitized snapshot of public tracked files. Link from README and Pages; GitHub README cannot execute interactive HTML.

## Boundaries

- No real resumes, postings, Cabinet pages, Obsidian vaults, writing corpora or provider accounts are read for this work.
- PDF text extraction and page/layout checks lower formatting risk. They do not guarantee ATS parsing, ranking, originality or an interview.
- Existing `template.html` and the two-argument `render.sh` path remain available for compatibility.
- User-reviewed generic shared phrases are not plagiarism evidence. A strict overlap gate detects literal four-word sequences; diagnostics must not print private passages by default.
- Diagrams describe confirmed code and the approval boundary, not imagined APIs. Animation is optional, accessible and paused under reduced motion.
- Finger-frame video restyling requires a hand-gesture clip and a paid external media operation. It has no useful role in repository exploration and is excluded.

## Verification

Use standard-library tests, synthetic fixtures, actual Chrome PDF rendering and Poppler extraction. Add failure-path CI tests and shared Linux/macOS Python checks. Preserve main's PR and required-test protection, and merge separate issue-sized PRs.

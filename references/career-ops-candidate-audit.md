# career-ops candidate-side audit

Audited 2026-11-24 from `career-ops-hq/career-ops` at commit `f8e4beb`, latest
release `career-ops-v1.40.0` ("No Silent Drops", 2026-11-10). Only candidate-side
behavior was considered. Employer-side recruiting, dashboard infrastructure and
generic CLI plumbing were excluded.

## Taken into cv-witness

- **Weight provenance.** career-ops labels requirement importance as stated in
  the JD, structural from the JD, or inferred, and never lets an inferred row
  reach the top importance band. `scripts/fit_score.py` now accepts
  `weight_basis` (`wording`, `structure`, `estimate`, `unlabelled`). If estimated
  weights carry at least half the assessed weight, a `great` band is capped to
  `good` with an explicit review reason. See `docs/fit-scoring.md`.
- **Title drift.** career-ops compares a tailored job title with the master CV's
  title for the same `{company, dates}`, warn-only. `scripts/check_cv_titles.py`
  does the same from canonical fields and `foundation.md`, and reports unmatched
  or ambiguous pairs instead of silently comparing the first match.
- **STAR+R story bank.** career-ops builds a reusable story bank where each
  story cites its source and leaves figures marked until the user verifies them.
  `scripts/star_worksheet.py` creates STAR+R prompts anchored to approved CV
  bullets; S/T/A/R and Reflection stay blank and must be filled from verified
  evidence.
- Earlier audits already ported the number fact gate from career-ops. The
  current `v1.40.0` additions around partial board reads, renderer-drop lint and
  verb-drift blocking are noted below rather than duplicated blindly.

## Deliberately not taken

- **Auto-apply and form filling.** cv-witness requires human review and has no
  browser submission integration. The candidate-side rule remains: draft fields,
  review autofill, press Submit yourself.
- **Contact discovery and LinkedIn messaging.** Useful, but it needs a verified
  people-search integration and explicit user consent before outreach. The
  existing recruiter-positioning reference covers the evidence discipline.
- **Portal scanner, dashboard, translation stack and hosted web UI.** These are
  product infrastructure, not CV quality gates, and would duplicate the
  existing sourcing scripts.
- **Verb-drift hard block and renderLint.** The current cv-witness gates already
  check numbers, placeholders, resource loading and layout. A hard block on
  rewording would conflict with legitimate tailoring; warn-only title drift is
  the narrower check with a clear failure mode. If a future renderer drops
  content silently, add a targeted lint for that renderer, not a generic clone.
- **Board `partial` status and robots-before-retry.** `check_posting_liveness.py`
  already has conservative `live`/`dead`/`suspicious`/`expired` states. Adding
  another status without a testable source signal would create a fake
  distinction.

## Boundary

Upstream behavior is a lead, not a guarantee. Every imported rule was checked
against the current source or mode documentation, adapted to cv-witness's
approved-baseline and honesty rules, and covered by local tests.

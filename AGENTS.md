# AGENTS.md - cv-witness

This repository is an agent skill for crafting and verifying job-application
CVs. It follows the SKILL.md standard and works with AdaL, Claude Code,
Codex, and any agent that reads AGENTS.md.

- Read `SKILL.md` first: it defines the workflow, the anti-fabrication gates,
  and the ATS parsing rules. Follow it.
- Private files: `foundation.md` (master resume) and `provenance.md`
  (verification notes) are gitignored. Never commit them, never send them to
  anyone, and never treat their contents as public data.
- Verify any external GitHub PR with `gh pr view <url>` before citing it as
  merged. Closed-unmerged work is never presented as merged.
- The posting informs emphasis and ordering, not invented facts or copied
  sentences. Run the shared posting checks; generic industry wording needs
  context review rather than automatic rewriting.
- Use `scripts/build_cv.py` for repeatable structured templates or `render.sh`
  for approved self-contained HTML. Select A4/Letter and an approved page limit;
  pass `--posting` when present. Failed checks must preserve previous output.
  Inspect every page and verify facts before delivery.
- Voice corpora and derived references are private style sources, never CV
  facts. Do not read real sources while developing; tests use synthetic prose.
  Imports require explicit source selection and human-authorship attestation.
- Run `CV_WITNESS_REQUIRE_PDF_TESTS=1 python3 -m unittest discover -s tests -q`
  with Python 3.11+, Chromium and Poppler to include actual export checks.
  Unit/corpus tests use the standard library and synthetic data.
- Regenerate public diagrams only from committed, reviewed public sources.
  Forbidden tracked paths must fail before any content read; do not scan this
  working tree or private vaults directly. See `docs/exploration.md`.

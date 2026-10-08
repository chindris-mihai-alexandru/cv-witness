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
- Never mirror the job description: the posting informs emphasis and ordering
  only. Rewrite any phrasing the CV shares with the posting; run
  `scripts/jd_overlap.py <cv> <posting>` to catch it mechanically.
- Render with `render.sh` and pass the mechanical checks in SKILL.md
  (pdftotext extraction, one page, no placeholders) before delivering.

# Contributing to cvwitness

Thanks for considering a contribution. The skill exists to keep CVs honest, so the contributing rules mirror that goal.

## Ground rules

- **Small and focused wins.** One change per PR — a doc fix, a template tweak, a verification improvement. Large rewrites are hard to review and will be asked to split.
- **Evidence over assertion.** If your change makes the skill claim something (a tool works, a platform is supported), include the command output or screenshot that proves it.
- **No personal data.** Never commit resumes, contact details, or `foundation.md`. PRs containing personal data will be closed.
- **Preserve the anti-fabrication gates.** Changes that weaken the `[FILL: …]` marker system, the merge-state checks, or the approval-before-render flow will be declined, however clever they are.
- **Conventional commits** (`feat:`, `fix:`, `docs:`, `chore:`) keep the history readable.

## Good first contributions

- Template variants (different type scales, a Letter-size path)
- Render support for more browsers/platforms
- Stronger checks in `render.sh` (e.g., detect empty output pages)
- Docs: clearer wording, more examples of good vs. inflated bullets

## Reporting bugs

Open an issue with the command you ran, the unexpected output, and what you expected. Redact any personal data first.

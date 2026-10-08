# Contributing to cv-witness

Thanks for considering a contribution. The skill exists to keep CVs honest, so the contributing rules mirror that goal.

## Ground rules

- **Small and focused wins.** One change per PR - a doc fix, a template tweak, a verification improvement. Large rewrites are hard to review and will be asked to split.
- **Evidence over assertion.** If your change makes the skill claim something (a tool works, a platform is supported), include the command output or screenshot that proves it.
- **No personal data.** Never commit resumes, contact details, or `foundation.md`. PRs containing personal data will be closed.
- **Preserve the anti-fabrication gates.** Changes that weaken the `[FILL: ...]` marker system, the merge-state checks, or the approval-before-render flow will be declined, however clever they are.
- **Conventional commits** (`feat:`, `fix:`, `docs:`, `chore:`) keep the history readable.

## Protected main branch

Changes to `main` go through a pull request. The `Voice corpus tests` gate must pass on an up-to-date branch, and review conversations must be resolved. The policy also applies to administrators and blocks force-pushes and branch deletion.

No second reviewer is required for this solo-maintained project; that does not bypass the PR, test or conversation checks. The policy snapshot is `.github/branch-protection.json`. It records the settings but does not apply them by itself.

The test workflow runs on every PR to `main`, including documentation-only changes, so a skipped path-filtered workflow cannot leave a required check pending. Run `python3 -m unittest discover -s tests -q` locally; tests use synthetic prose only.

## Good first contributions

- Template variants (different type scales, a Letter-size path)
- Render support for more browsers/platforms
- Stronger checks in `render.sh` (e.g., detect empty output pages)
- Docs: clearer wording, more examples of good vs. inflated bullets

## Reporting bugs

Open an issue with the command you ran, the unexpected output, and what you expected. Redact any personal data first.

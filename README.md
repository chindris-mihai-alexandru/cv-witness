# cv-forge

An [AdaL](https://adalagent.ai/) skill that turns **verified experience** into tailored, ATS-safe, one-page CVs — evidence-first and fabrication-proof.

Most CV tailoring fails in one of two ways: it invents polish the candidate cannot back up, or it ships a wall of keywords that parses badly and reads worse. cv-forge takes the opposite stance. Every claim on the page must trace to a source you control: a master resume, a merged pull request, a confirmed fact. When evidence is missing, the skill says so instead of filling the gap.

## What it does

- **Maps a job posting to your evidence.** Required vs. preferred qualifications are matched against your master resume, your GitHub record, and facts you confirm — with unsupported requirements flagged as gaps, not papered over.
- **Verifies external claims.** Any open-source PR cited on the CV is merge-checked against the GitHub API first. Closed-unmerged work is never presented as merged.
- **Tailors without inflating.** Reorders and rephrases what is real; uses `[FILL: …]` markers where a metric is plausible but unconfirmed, so nothing fabricated slips through.
- **Renders an ATS-safe PDF.** Single column, no tables, one muted accent, real text everywhere — via headless Chrome.

## Install

```bash
git clone https://github.com/Mihai-Codes/cv-forge.git ~/.adal/skills/cv-forge
```

Requirements: [AdaL CLI](https://adalagent.ai/), a Chrome-family browser (PDF rendering), and the [`gh` CLI](https://cli.github.com/) authenticated for merge-state verification. Claude Code-compatible skill format.

## Usage

Point AdaL at a job posting and ask for a tailored CV. Typical prompts:

> "Tailor my CV for this role: <posting URL or text>"

> "Find roles matching my profile and draft the top application"

The skill gathers the posting, maps it to evidence, proposes the tailored content, and renders the final PDF to `~/Downloads/` after you approve the content.

## Repository structure

```text
SKILL.md         # the skill: workflow, rules, safety boundaries
template.html    # ATS-safe one-page layout (single column, inline SVG contact icons)
render.sh        # HTML → PDF via headless Chrome/Brave/Edge/Chromium
```

**Intentionally not in this repo:** `foundation.md`, the private master resume the skill reads at runtime. Keep yours at `~/.adal/skills/cv-forge/foundation.md` — it is personal data and must never be committed here.

## Verification principles

1. Every experience, metric, and credential traces to the master resume, a confirmed fact, or a public artifact.
2. External PRs and issues are checked for merge/state before they are cited.
3. Unverifiable but plausible metrics become `[FILL: …]` markers, never guesses.
4. Expired or in-progress credentials are labelled as such or omitted.
5. No ATS scores, rankings, or interview promises — those cannot be honestly guaranteed.

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Small, focused PRs get the fastest review; non-code contributions (docs, template variants, render targets) are as valuable as code.

## Roadmap

- [ ] Split verification notes out of the master resume into a structured evidence file
- [ ] Portable paths (currently reflects the author's machine)
- [ ] Additional render targets (DOCX via a host-assistant document flow)
- [ ] Template variants per career lane (support, DevOps, application engineering)

## License

[MIT](LICENSE)

Personal project by [cv-witness contributors](https://mihai.codes). Not affiliated with or endorsed by Amazon, Yubico, or any employer named in examples.

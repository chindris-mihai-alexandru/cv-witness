<p align="center">
  <img src="assets/banner.png" alt="cv-forge — evidence-first CV tailoring" width="100%">
</p>

<h1 align="center">cv-forge</h1>

<p align="center">
  <a href="#verification-principles"><img alt="output ATS-safe" src="https://img.shields.io/badge/output-ATS%E2%80%91safe-3f3f46"></a>
  <a href="https://github.com/Mihai-Codes/cv-forge/actions"><img alt="no fabrication" src="https://img.shields.io/badge/anti%E2%80%91fabrication-gated-FF5898"></a>
  <a href="https://github.com/rezi-io/rezi-mcp"><img alt="Rezi MCP optional" src="https://img.shields.io/badge/Rezi%20MCP-optional-4c8bf5"></a>
  <a href="https://github.com/Mihai-Codes/cv-forge/blob/main/LICENSE"><img alt="License MIT" src="https://img.shields.io/github/license/Mihai-Codes/cv-forge"></a>
  <a href="https://github.com/Mihai-Codes/cv-forge/pulls"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen"></a>
</p>

An [AdaL](https://adalagent.ai/) skill that turns **verified experience** into tailored, ATS-safe, one-page CVs — evidence-first and fabrication-proof. Works as a standalone personal skill or in tandem with the [Rezi MCP](https://github.com/rezi-io/rezi-mcp).

Most CV tailoring fails in one of two ways: it invents polish the candidate cannot back up, or it ships a wall of keywords that parses badly and reads worse. cv-forge takes the opposite stance. Every claim on the page must trace to a source you control: a master resume, a merged pull request, a confirmed fact. When evidence is missing, the skill says so instead of filling the gap.

## What it does

- **Maps a job posting to your evidence.** Required vs. preferred qualifications are matched against your master resume, your GitHub record, and facts you confirm — with unsupported requirements flagged as gaps, not papered over.
- **Verifies external claims.** Any open-source PR cited on the CV is merge-checked against the GitHub API first. Closed-unmerged work is never presented as merged.
- **Tailors without inflating.** Reorders and rephrases what is real; uses `[FILL: …]` markers where a metric is plausible but unconfirmed, so nothing fabricated slips through.
- **Renders an ATS-safe PDF.** Single column, no tables, one muted accent, real text everywhere — via headless Chrome.

## Works with Rezi (optional)

If you connect the [Rezi MCP server](https://github.com/rezi-io/rezi-mcp), the skill can use your Rezi account as a live evidence source: listing and reading your saved resumes, checking the current section schema, and — only with your explicit approval — writing tailored content back to a chosen resume, then reading it back to verify. Reads are the default; writes are always opt-in. Without Rezi, the skill runs entirely on local sources.

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
assets/          # banner
```

**Intentionally not in this repo:** `foundation.md`, the private master resume the skill reads at runtime. Keep yours at `~/.adal/skills/cv-forge/foundation.md` — it is personal data and must never be committed here.

## Verification principles

1. Every experience, metric, and credential traces to the master resume, a confirmed fact, or a public artifact.
2. External PRs and issues are checked for merge/state before they are cited.
3. Unverifiable but plausible metrics become `[FILL: …]` markers, never guesses.
4. Expired or in-progress credentials are labelled as such or omitted.
5. No ATS scores, rankings, or interview promises — those cannot be honestly guaranteed. Output is instead validated mechanically: `pdftotext` extraction, one-page check, placeholder scan, and the ATS checklist in `SKILL.md`.

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Small, focused PRs get the fastest review; non-code contributions (docs, template variants, render targets) are as valuable as code.

## Roadmap

- [x] Fix bullet-marker clipping and header/footer spacing in the template (2026-10)
- [x] Merge-state verification for external PRs before citing (2026-10)
- [ ] Split verification notes out of the master resume into a structured evidence file
- [ ] Portable paths (currently reflects the author's machine)
- [ ] Drive a host assistant's native DOCX flow end-to-end (Amazon Quick, in progress)
- [ ] Additional render targets and template variants per career lane

## License

[MIT](LICENSE)

Personal project by [cv-witness contributors](https://mihai.codes). Not affiliated with or endorsed by Amazon, Yubico, Rezi, or any employer named in examples.
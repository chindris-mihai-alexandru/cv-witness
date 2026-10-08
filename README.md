<p align="center">
  <img src="assets/banner.png" alt="cv-witness: tailored CVs, nothing invented" width="100%">
</p>

<h1 align="center">cv-witness</h1>

<p align="center">
  <a href="https://github.com/Mihai-Codes/cv-witness/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/Mihai-Codes/cv-witness?color=FF5898&labelColor=1b222c"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-2b3542?labelColor=1b222c"></a>
  <a href="https://github.com/Mihai-Codes/cv-witness/pulls"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-2b3542?labelColor=1b222c"></a>
</p>

<p align="center">
  <a href="https://mihai-codes.github.io/cv-witness/">Website</a> ·
  <a href="#install">Install</a> ·
  <a href="https://github.com/Mihai-Codes/cv-witness/issues/1">Roadmap</a>
</p>

An open-source agent skill for drafting and reviewing a CV from your real experience. It helps you select relevant work, trace claims to a source and inspect the exported document. You review the facts and wording before applying.

## How cv-witness differs

The job posting guides emphasis and ordering. It should not become a script for rewriting your history. Describe the work you did, keep accurate technical terms, and flag missing facts instead of inventing them.

The skill asks your agent to:

- Check dates, credentials, metrics and contribution claims against your sources. Verify a public pull request's merge state before calling it merged.
- Use `[FILL: ...]` markers in a draft when information is missing, then resolve or remove them before delivery.
- Run the phrase-overlap script and review shared wording in context. A common technical phrase is not proof of copying and need not be changed just to avoid a match.
- Inspect the exported text, page count, placeholders and layout before sending the CV.

These are workflow instructions, not guarantees an agent cannot bypass. The PDF renderer creates a file; it does not automatically certify its contents. No ATS parsing result, ranking, exact voice match or interview is promised.

## Install

One root `SKILL.md` is shared by every installation. The template and scripts live beside it, so there are no duplicate skills or recursive directory links.

### AdaL

```sh
git clone https://github.com/Mihai-Codes/cv-witness.git ~/.adal/skills/cv-witness
```

### Claude Code

Send these as two separate commands inside Claude Code:

```text
/plugin marketplace add Mihai-Codes/cv-witness
/plugin install cv-witness@cv-witness
```

The plugin manifest points to the root skill. Alternatively, install a personal skill:

```sh
git clone https://github.com/Mihai-Codes/cv-witness.git ~/.claude/skills/cv-witness
```

### Codex

```sh
git clone https://github.com/Mihai-Codes/cv-witness.git ~/.agents/skills/cv-witness
```

For other hosts, follow their skill-discovery instructions or ask the agent to read the root `SKILL.md`. If the destination already contains a clone, update it instead of overwriting your private sources.

## Compatibility and tools

### Agent hosts

<p>
  <a href="https://docs.sylph.ai/"><img alt="AdaL skill" src="https://img.shields.io/badge/AdaL-skill-2b3542?style=flat&labelColor=1b222c"></a>
  <a href="https://code.claude.com/docs/en/plugins/overview"><img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude%20Code-plugin-2b3542?style=flat&labelColor=1b222c&logo=anthropic&logoColor=white"></a>
  <a href="https://learn.chatgpt.com/docs/build-skills"><img alt="Codex skill" src="https://img.shields.io/badge/Codex-skill-2b3542?style=flat&labelColor=1b222c"></a>
</p>

AdaL, Claude Code and Codex have installation paths above. Other hosts may read the same skill format; they are not all independently tested.

### Local tools

<p>
  <img alt="Python 3" src="https://img.shields.io/badge/Python-3-2b3542?style=flat&labelColor=1b222c&logo=python&logoColor=white">
  <img alt="Chromium PDF rendering" src="https://img.shields.io/badge/Chromium-PDF-2b3542?style=flat&labelColor=1b222c&logo=googlechrome&logoColor=white">
  <a href="https://cli.github.com/"><img alt="GitHub CLI" src="https://img.shields.io/badge/GitHub-CLI-2b3542?style=flat&labelColor=1b222c&logo=github&logoColor=white"></a>
</p>

The current `render.sh` targets macOS and discovers installed Chrome, Brave, Edge or Chromium applications. The overlap script uses Python 3 and `pdftotext` for PDF input. Review instructions also use `pdfinfo`; both PDF tools are supplied by Poppler. Authenticated GitHub CLI is used for contribution checks, not for the overlap script.

### Optional services

<p>
  <a href="https://github.com/rezi-io/rezi-mcp"><img alt="Rezi MCP optional" src="https://img.shields.io/badge/Rezi%20MCP-optional-2b3542?style=flat&labelColor=1b222c"></a>
  <img alt="Amazon Quick optional" src="https://img.shields.io/badge/Amazon%20Quick-optional-2b3542?style=flat&labelColor=1b222c">
</p>

Rezi can provide resume facts from an account you choose. Writes require your explicit approval and a read-back check. Amazon Quick is a documented host-native DOCX workflow, not a bundled integration. Neither service is required for the local PDF path.

## Usage

Ask your agent:

> "Draft a CV from my verified experience for this role: [paste the posting URL or text here]. Keep my voice and show me the wording before exporting."

Provide a master resume and any verification notes privately. Review the selected facts, resolve unanswered questions, and approve the draft before rendering. The local workflow saves the final PDF to your configured output directory, which defaults to `~/Downloads/`.

For phrase review:

```sh
python3 scripts/jd_overlap.py CV.pdf posting.txt
```

The script compares literal word sequences. `--strict` exits with a failure when any shared run of four or more words is found, including ordinary industry phrases. Use that flag only when this behavior fits your review process; a pass is not an ATS or originality certification.

## Repository structure

```text
SKILL.md                 # canonical skill instructions
AGENTS.md                # short contributor/agent entry point
.claude-plugin/          # plugin and marketplace manifests
.github/workflows/       # GitHub Pages deployment
index.html               # landing page, styles and interaction code
assets/                  # branding, hero atmosphere and rendered sample
examples/sample-cv.json  # fictional public sample data
template.html            # local CV layout
render.sh                # macOS HTML-to-PDF renderer
scripts/jd_overlap.py    # phrase-overlap review tool
scripts/render_sample.py # reproduce and validate the public sample
```

README, contribution guidance, changelog and license stay at the root. The small static site needs no framework, package install or generated bundle.

`foundation.md` and `provenance.md` are private local sources excluded by `.gitignore`. They are not included in the public repository. Keep them outside public artifacts and remember that your agent provider's data policy applies when it reads them.

The banner source is `assets/banner.html`; it reuses `assets/mark.svg`. Render it in a Chromium browser at 2100 × 900 CSS pixels when updating the published `assets/banner.png`.

## Reproduce the public sample

The website shows a screenshot of [this PDF](assets/sample-cv.pdf), rendered from the unchanged `template.html` using `render.sh`. The candidate, employer, credentials and achievements in [the source fixture](examples/sample-cv.json) are fictional. No private resume data is used.

```sh
python3 scripts/render_sample.py
```

The helper fills the canonical template, runs the existing renderer, checks one-page output and text extraction, then creates the PDF and screenshot in `assets/`. The site links to both the PDF and its source; this demonstrates the current layout, not universal ATS compatibility.

## Contributing and status

See [CONTRIBUTING.md](CONTRIBUTING.md). Small changes with reproducible checks are easiest to review.

[Releases](https://github.com/Mihai-Codes/cv-witness/releases) describe shipped versions, [CHANGELOG.md](CHANGELOG.md) records changes, and [roadmap issue #1](https://github.com/Mihai-Codes/cv-witness/issues/1) links the planned work. Implementation issues hold their own scope and acceptance criteria.

## License

[MIT](LICENSE)

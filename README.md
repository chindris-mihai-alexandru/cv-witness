<p align="center">
  <img src="assets/banner.png" alt="cv-witness: tailored CVs, nothing invented" width="100%">
</p>

<h1 align="center">cv-witness</h1>

<p align="center">
  <a href="https://github.com/chindris-mihai-alexandru/cv-witness/actions/workflows/voice-tests.yml"><img alt="Tests" src="https://img.shields.io/github/actions/workflow/status/chindris-mihai-alexandru/cv-witness/voice-tests.yml?branch=main&label=tests&color=2b3542&labelColor=1b222c"></a>
  <a href="https://github.com/chindris-mihai-alexandru/cv-witness/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/chindris-mihai-alexandru/cv-witness?color=FF5898&labelColor=1b222c"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-2b3542?labelColor=1b222c"></a>
  <a href="https://github.com/chindris-mihai-alexandru/cv-witness/pulls"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-2b3542?labelColor=1b222c"></a>
</p>

<p align="center">
  <a href="https://chindris-mihai-alexandru.github.io/cv-witness/">Website</a> ·
  <a href="#install">Install</a> ·
  <a href="https://github.com/chindris-mihai-alexandru/cv-witness/issues/1">Roadmap</a>
</p>

An open-source agent skill for drafting and reviewing a CV from your real experience. It helps you select relevant work, trace claims to a source and inspect the exported document. You review the facts and wording before applying.

## How cv-witness differs

The posting guides emphasis and ordering, not facts. Describe your own work in your own words, keep accurate technical terms, and flag gaps instead of inventing them.

The agent follows five checkpoints:

- **Evidence:** tie dates, credentials, metrics and contributions to your sources. Verify a public PR's merge state before calling it merged; use `check_cv_numbers.py` and `check_cv_titles.py` for unsupported figures and title drift. LinkedIn data comes only from your local export via `linkedin_export_import.py` and `linkedin_profile_diff.py`; public Hugging Face/GitHub findings are leads to verify. See the [LinkedIn export workflow](references/linkedin-export-workflow.md).
- **Posting:** before tailoring, check liveness, posting integrity and role clarity. Treat suspicious or client-side results as uncertain, not closed. Follow the [candidate-side rules](references/candidate-safety-and-decision-rules.md); optional [fit scoring](docs/fit-scoring.md) is advisory.
- **Draft:** use `[FILL: ...]` for missing facts. Run payload lint, phrase overlap, `jd_coverage.py`, humane wording and `cover_letter_check.py` as review aids. They flag wording risks; they are not truth verdicts or ATS scores. Common technical terms are not proof of copying.
- **Export:** inspect bullets, extracted text, section order, dates, page count and balanced page fill with `bullet_audit.py` and `verify_layout.py`, then run `ats_validate.py`. Use the TXT fallback where accepted. No local check guarantees a vendor parser.
- **Optional:** `star_worksheet.py` and `story_provenance.py` support evidence-backed interview prep. RMS v2 metadata is an invisible XMP layer, not an ATS guarantee.

The renderer creates a file; it does not certify its contents. No ATS result, ranking, exact voice match or interview is promised.

## Install

One root `SKILL.md` is shared by every installation. The template and scripts live beside it, so there are no duplicate skills or recursive directory links.

### AdaL

```sh
git clone https://github.com/chindris-mihai-alexandru/cv-witness.git ~/.adal/skills/cv-witness
```

### Claude Code

Send these as two separate commands inside Claude Code:

```text
/plugin marketplace add chindris-mihai-alexandru/cv-witness
/plugin install cv-witness@cv-witness
```

The plugin manifest points to the root skill. Alternatively, install a personal skill:

```sh
git clone https://github.com/chindris-mihai-alexandru/cv-witness.git ~/.claude/skills/cv-witness
```

### Codex

```sh
git clone https://github.com/chindris-mihai-alexandru/cv-witness.git ~/.agents/skills/cv-witness
```

For other hosts, follow their skill-discovery instructions or ask the agent to read the root `SKILL.md`. If the destination already contains a clone, update it instead of overwriting your private sources.

Before first use, review the personal configuration and authoring preferences in `SKILL.md`. Set your own CV-guide, application-log and output paths; the owner's Cabinet paths and Quick preference are examples, not requirements for your setup.

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
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-2b3542?style=flat&labelColor=1b222c&logo=python&logoColor=white">
  <img alt="Chromium PDF rendering" src="https://img.shields.io/badge/Chromium-PDF-2b3542?style=flat&labelColor=1b222c&logo=googlechrome&logoColor=white">
  <a href="https://cli.github.com/"><img alt="GitHub CLI" src="https://img.shields.io/badge/GitHub-CLI-2b3542?style=flat&labelColor=1b222c&logo=github&logoColor=white"></a>
</p>

`render.sh` delegates to the shared Python 3.11+ renderer, which discovers Chromium-family browsers on Linux and macOS. Poppler supplies `pdftotext` and `pdfinfo` for pre-delivery checks; `pdftoppm` creates sample previews. Authenticated GitHub CLI is used for contribution checks, not for rendering or phrase review.

### Optional services

<p>
  <a href="https://github.com/rezi-io/rezi-mcp"><img alt="Rezi MCP optional" src="https://img.shields.io/badge/Rezi%20MCP-optional-2b3542?style=flat&labelColor=1b222c"></a>
  <a href="https://github.com/superdesigndev/treg"><img alt="Treg jobs-api optional" src="https://img.shields.io/badge/Treg%20jobs--api-optional-2b3542?style=flat&labelColor=1b222c"></a>
  <img alt="Amazon Quick optional" src="https://img.shields.io/badge/Amazon%20Quick-optional-2b3542?style=flat&labelColor=1b222c">
</p>

Rezi can provide resume facts from an account you choose. Writes require your explicit approval and a read-back check. The Treg jobs-api is an optional paid catalog for finding and ranking roles, the hiring manager and posted pay before tailoring; it is used through its own upstream CLI/MCP, not a bundled client (see `references/treg-jobs-sourcing.md`). Amazon Quick is a documented host-native DOCX workflow, not a bundled integration. None of these services is required for the local PDF path.

## Usage

Run the command examples from your cloned skill directory. The Python tools use the standard library; PDF export also needs a Chromium-family browser and Poppler. Keep real inputs and outputs outside the public `examples/` and `assets/` folders.

Ask your agent:

> "Draft a CV from my verified experience for this role: [paste the posting URL or text here]. Keep my voice and show me the wording before exporting."

Provide a master resume, the latest candidate-approved CV (or a specific design reference), and verification notes privately. The approved CV is the default design baseline across authoring tools; ask before changing its layout or section order. Review the selected facts and approve the draft before rendering. The agent workflow uses the output directory configured in `SKILL.md`; standalone build and render commands require an explicit output path.

For phrase review:

```sh
python3 scripts/jd_overlap.py CV.pdf posting.txt
```

The script compares literal word sequences. `--strict` fails on any shared run of four or more words, including ordinary industry phrases. Reports give counts and positions, including repeated occurrences; `--show-phrases` is an explicit opt-in for private wording. A pass is not an ATS or originality certification.

For checked output, use `sh render.sh approved.html output.pdf a4 --posting posting.txt`. The renderer validates a temporary PDF before publishing and preserves previous output if any check fails. It rejects external/resource-loading content in the HTML, including CSS escapes that disguise `@import` or `url()`. This narrow preflight is not a general-purpose hostile-HTML sandbox. Selecting a posting uses strict overlap checks by default; choose `--overlap-policy review` explicitly when shared generic wording should be reviewed rather than blocked.

To preserve an approved CV's exact look, render tailored fields through the canonical house-style template:

```sh
python3 scripts/render_sample.py --fields fields.json --output CV.pdf --margin-mm 15
```

This fills `template.html` with the same checked renderer as the public sample, so margins, header, contact icons and section order match the approved baseline. `--margin-mm` sets uniform page margins (the approved baseline uses 15mm); omit it to keep the template defaults. Scalar fields are HTML-escaped; block fields (`ROLES_BLOCK`, `PROJECTS_BLOCK`, `SKILLS_BLOCK`, `CERTS_BLOCK`, `EDUCATION_BLOCK`, `SUMMARY_2`) are trusted HTML, and the field set must match the template placeholders exactly.

For a PDF exported from another authoring tool:

```sh
python3 scripts/check_cv.py exported.pdf \
  --paper a4 --max-pages 1 \
  --expected-text "Alex Morgan" \
  --ordered-text "Professional Summary" \
  --ordered-text "Skills" \
  --ordered-text "Professional Experience" \
  --strict-ordered-text \
  --posting posting.txt
```

Add critical text as `--expected-text` arguments and section headings in approved order as repeated `--ordered-text` flags. Add `--strict-ordered-text` for standalone heading lines in generated CVs. This checks extracted landmarks, not every ATS's reading order or field parsing. Compare the export visually with the approved CV and review any employer autofill before submission. Parsing varies by platform: [Greenhouse documents reasons parsing can fail](https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse), while [Rezi describes its score as guidance, not a particular ATS result](https://www.rezi.ai/rezi-docs/the-rezi-score-explained). Exit codes are `0` for a policy pass, `1` for failed checks and `2` for input or tool errors. See [delivery checks](docs/delivery-checks.md) for limits and privacy-safe diagnostics.

## Repeatable career-lane templates

For a local CV with more than the legacy template's fixed role slots, provide approved structured wording:

```sh
python3 scripts/build_cv.py approved-cv.json output.pdf \
  --lane engineering --paper a4 --max-pages 1 \
  --posting selected-posting.txt
```

Engineering, Operations/Support, Research, Management, Security and Customer-Success are section-order presets over one single-column layout. Roles repeat, empty optional sections are omitted, and A4/Letter exports use the same delivery checks. The builder checks that its selected section headings extract in the chosen order. These are product layouts, not replacements for a candidate's existing design; obtain approval before switching. The single-column preset is a parsing-risk recommendation, not a requirement to redesign an approved two-column CV. Longer CVs need an explicit approved page limit; text is never dropped or silently shrunk. See the [template contract](docs/template-contract.md) and [fictional structured example](examples/structured-cv.json).

## Explore the repository

[Open the interactive project guide](https://chindris-mihai-alexandru.github.io/cv-witness/assets/explore/) for the animated workflow, searchable source map, three guided reading tours and eight fictional template PDFs.

<p align="center">
  <a href="https://chindris-mihai-alexandru.github.io/cv-witness/assets/explore/workflow.html"><img src="assets/explore/workflow-preview.svg" alt="Approved wording passes through the shared layout, temporary PDF and delivery checks. Failure preserves prior output; passing output still needs visual and factual review." width="520"></a>
</p>

[Workflow](https://chindris-mihai-alexandru.github.io/cv-witness/assets/explore/workflow.html) · [Source map](https://chindris-mihai-alexandru.github.io/cv-witness/assets/explore/codegraph.html) · [Regeneration and limits](docs/exploration.md)

The README preview has a fixed light background and dark labels in either GitHub theme. Open it for the interactive workflow, whose theme and pause controls remain available. The full maps work offline and respect reduced motion. They describe verified workflow and public source structure, not live telemetry; private resumes and writing corpora are excluded.

## Optional candidate voice reference

Use your own selected writing as a private style reference. The local corpus tool accepts text/Markdown (including Cabinet pages and Obsidian notes), Sanity exports, and a common original-text format for other CMS or memory exports. It filters authors and message roles, excludes labelled generated/quoted content, and measures writing habits without training a model or uploading text.

```sh
python3 scripts/voice_corpus.py import /absolute/path/to/approved-writing \
  --format text --author my-author-id --language en --genre blog \
  --attest-human --dry-run
```

Confirm that the selected prose is your own human-written original before using `--attest-human`. Remove `--dry-run` only after reviewing the counts. Cabinet agent outputs, memory summaries and benchmark data are not original writing; names of source tools do not establish authorship.

The store defaults to `~/.cv-witness/voice`. Generate a profile, optionally approve private excerpts, and use it to guide a draft while keeping resume facts separate. No exact voice-match score is promised. See the [voice corpus guide](docs/voice-corpus.md) for Sanity fields, message formats, provider limits, privacy, updates and deletion. The voice tool requires Python 3.11+; it has no third-party Python dependencies.

## Repository structure

The short table below orients new readers. The complete grouped inventory of scripts and directories lives in the [repository map](docs/repository-map.md); the [interactive source map](https://chindris-mihai-alexandru.github.io/cv-witness/assets/explore/codegraph.html) shows the code graph.

| Location | Purpose |
| --- | --- |
| `SKILL.md`, `AGENTS.md` | Agent workflow and contributor guidance. |
| `scripts/`, `templates/` | CV building, validation, rendering, voice references and regeneration tools. |
| `references/` | Candidate-side rules plus public company lists used by screening and network tools (no personal data). |
| `docs/`, `examples/` | Usage guides, contracts and fictional inputs. |
| `assets/explore/` | Interactive maps and the fictional PDF gallery. |
| `tests/` | Synthetic contracts and actual PDF export regressions. |
| `.github/`, `.claude-plugin/` | CI, deployment, branch-policy settings and plugin manifests. |
| `index.html`, `render.sh`, `template.html` | Website entrypoint, checked-render command and canonical house-style CV layout. |

README, contribution guidance, changelog and license stay at the root. The small static site needs no framework, package install or generated bundle.

`foundation.md` and `provenance.md` are private local sources excluded by `.gitignore`. They are not included in the public repository. Keep them outside public artifacts and remember that your agent provider's data policy applies when it reads them. Tailored CVs and the `cvs/` folder are gitignored too: never commit a tailored CV, job-specific notes, or real candidate/employer details to this public repo. Test and example fixtures use fictional people and reserved `example.*` domains (enforced by `tests/test_no_personal_data.py`).

The banner source is `assets/banner.html`; it reuses `assets/mark.svg`. Render it in a Chromium browser at 2100 × 900 CSS pixels when updating the published `assets/banner.png`.

## Reproduce the public sample

The website shows a screenshot of [this PDF](assets/sample-cv.pdf), rendered from the unchanged `template.html` using `render.sh`. The candidate, employer, credentials and achievements in [the source fixture](examples/sample-cv.json) are fictional. No private resume data is used.

```sh
python3 scripts/render_sample.py
```

The helper fills the canonical template, runs the existing renderer, checks one-page output and text extraction, then creates the PDF and screenshot in `assets/`. The site links to both the PDF and its source; this demonstrates the current layout, not universal ATS compatibility.

## Versioning

Stable from 1.0.0. See [docs/versioning.md](docs/versioning.md) for the release policy.

## Contributing and status

See [CONTRIBUTING.md](CONTRIBUTING.md). Small changes with reproducible checks are easiest to review. Run `CV_WITNESS_REQUIRE_PDF_TESTS=1 python3 -m unittest discover -s tests -q` with Chromium and Poppler to include actual export checks. All fixtures are synthetic; no personal corpus or connected account is needed.

[Releases](https://github.com/chindris-mihai-alexandru/cv-witness/releases) and [CHANGELOG.md](CHANGELOG.md) record shipped changes. The [initial roadmap](https://github.com/chindris-mihai-alexandru/cv-witness/issues/1) is complete; its closed sub-issues retain implementation and verification notes. Propose future work in a new, focused issue.

## License

[MIT](LICENSE)

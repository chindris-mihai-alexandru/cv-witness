# Changelog

All notable changes to cv-witness are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versioning follows
[Semantic Versioning](https://semver.org/). Versions before 0.4.0 were
developed in a private history that was purged when the repository went
public; their entries are consolidated summaries, not commit-for-commit notes.

## [Unreleased]

### Added

- Layout gate: `cv_layout.check_page_fill` fails any page whose bottom whitespace exceeds its top whitespace by more than 20pt (`layout_bottom_whitespace`). The mandatory `scripts/verify_layout.py` delivery gate now passes that tolerance, so an underfilled page with a large empty footer cannot be delivered. Sparse internal render fixtures remain valid because render-time geometry checks leave page fill opt-in.
- Site: the fictional sample and project page now reflect the balanced-spacing layout and the page-fill gate.

### Fixed

- Pages deploy: split artifact build and deployment into separate jobs and moved to current `checkout`, `configure-pages`, `upload-pages-artifact` and `deploy-pages` releases. The former single-job workflow uploaded the artifact successfully but the immediate metadata lookup sometimes found zero artifacts.

### Versioning policy

From 1.0.0 onward, releases follow a slower SemVer cadence: patch for backwards-compatible bug fixes, minor for new compatible scripts/flags/docs, and major only for breaking template fields, CLI output contracts or privacy/safety behavior. Multiple related fixes are grouped into one release instead of tagging every work session. Existing 0.x tags are not renumbered.

## [1.0.0] - 2026-11-25

### Fixed

- Bullet audit: recognizes both `<ul class="role-sub">` and the approved template's `<div class="role-sub"><ul>` shape. Contract checks now see all role/project blocks instead of silently reporting zero blocks.
- Bullet audit: when `--source-html` is supplied, the Action/Metric/Tool review uses the exact `<li>` text from the authoring HTML instead of merged PDF text lines.
- Template: repaired the malformed nested SVG for the Hugging Face contact link. The header now shows a legible `HF` text label; regenerated `assets/sample-cv.pdf` and `assets/sample-cv.png`.

## [0.9.6] - 2026-11-25

### Added

- Safe LinkedIn export workflow: `scripts/linkedin_export_import.py` creates a local, privacy-filtered snapshot from the candidate's own export; `scripts/linkedin_profile_diff.py` performs alias-aware read-only comparison and writes a private preview draft. Based on the documented LinkedIn My Profile MCP read/resolve/preview design, with no write tool, session cookies or scraping. See `references/linkedin-export-workflow.md`.

## [0.9.5] - 2026-11-24

### Changed

- Number fact gate: equivalent claim spellings are canonicalized before comparison — percentage words and LaTeX `\%`, currency codes/words and postfix symbols, spelled-out counts with digits, and `-fold`/`x` multipliers. A reworded figure can no longer bypass the gate; the check remains lexical, not a context or truth verdict.

## [0.9.4] - 2026-11-24

### Added

- `references/candidate-safety-and-decision-rules.md`: late audit rules for candidate-side decisions only — two-pass job importance, never running recruiter code, visible do-not-apply records, opt-in cross-channel dedupe, no unsolicited salary expectations, fee/work-rights risk, ATS "own words" limits, retracted claims, no fabricated interview material, calibration floors and data portability.

### Changed

- Liveness: transient HTTP 429/5xx is suspicious; question-form closure and completed forms no longer close a posting; "job/role has been filled" is recognized.
- Cover-letter check: flags em/en dashes, curly quotes and stock openers in addition to existing hype checks.
- Role clarity: supervisor status requires a named department; success measure and horizon must share a sentence; quotes capped at 240 characters; empty posting retains six-point shape without fabricated questions.
- Story provenance: same number + unit + shared metric tokens are required to call a figure existing; a story-level user-cannot-confirm marker masks every figure in that story; Unicode metric tokens are preserved.
- ATS headings: common EU/global aliases are recognized; unrecognized languages are reported explicitly.
- JD coverage: `--fields fields.json` adds advisory reverse coverage of CV skills not named by supplied JD terms.

## [0.9.3] - 2026-11-24

### Added

- Advisory posting integrity (`scripts/posting_integrity.py`): hidden blocks, hidden-only URLs, invisible Unicode, instruction-shaped lines and mixed-script words in job text. Detection is triage, not a security guarantee; posting text remains data.
- Advisory role clarity (`scripts/role_clarity.py`): six-point present/partial/missing check with exact quoted evidence and soft-verb load, plus an `askBeforeYouCommit` list when three or more points are missing.
- Advisory ATS payload lints (`scripts/payload_lint.py`): employer-in-role, parenthetical-in-company, multiple date ranges and nonstandard skills heading. Findings are human decisions, never automatic edits.
- Story number provenance (`scripts/story_provenance.py`): classifies figures in STAR+R stories as existing, user-cannot-confirm or derived-unverified against approved sources.

### Changed

- The career-ops audit record now distinguishes implemented candidate-side gates from upstream features deliberately excluded.

## [0.9.2] - 2026-11-24

### Added

- `scripts/check_cv_titles.py`: advisory job-title drift check pairing tailored roles with `foundation.md` by company and dates. Mismatches, unmatched and ambiguous pairs are reported; title changes remain a human decision.
- `scripts/star_worksheet.py`: STAR+R interview prompts anchored to approved bullets, with S/T/A/R and Reflection left blank for evidence-backed completion.
- `references/career-ops-candidate-audit.md`: records the 2026-11-24 candidate-side audit of `career-ops-hq/career-ops` and why other upstream features were not copied.

### Changed

- `scripts/fit_score.py` accepts `weight_basis` (`wording`, `structure`, `estimate`, `unlabelled`) and reports weight-basis shares. If estimated weights carry at least half the assessed weight, a `great` band is capped to `good` with an explicit review reason. See `docs/fit-scoring.md`.

## [0.9.1] - 2026-11-24

### Added

- Parser-safe plain-text export (`scripts/ats_text_export.py`): one-column real text with standard headings from the same approved fields, for TXT uploads and manual ATS autofill review. It is a fallback channel, not a new CV design.
- `scripts/rms_metadata.py` prints the full synthetic 1,274-key v2 template, maps canonical CV fields to RMS keys, and appends XMP through a PDF incremental update without changing visible text. `--verify` reports producer and counts without printing PII.
- `docs/rms-v2-metadata.md` records the upstream staleness, the absence of a declarative template, and the limits of the standard: an RMS-aware parser copies supplied fields exactly, but no major ATS is documented as consuming RMS.

### Changed

- `scripts/ats_validate.py` now accepts country-specific degrees such as B.Sc., checks PDF size against Greenhouse's documented 2.5 MB parsing limit, and verifies embedded fonts. It still cannot guarantee vendor parsing.
- The RMS writer validates key names, count/index bounds, timestamps, booleans and date formats; verifies the new startxref and XMP round-trip; and rejects encrypted, xref-stream or already-tagged PDFs. Duplicate metadata updates must be re-rendered from source.

## [0.9.0] - 2026-11-24

### Added

- Public-footprint enrichment: `scripts/public_footprint.py` reads Hugging Face profiles and verifies GitHub pull-request merges, with a live `pr-summary` replacing static hand-counted PR numbers. Dict-shaped HF payloads, CLI banner-before-JSON output and official HF branding are handled.
- Advisory delivery checks: `scripts/jd_coverage.py` reports exact posting-term presence without claiming an ATS score; `scripts/cover_letter_check.py` checks length, placeholders, hype and work-rights contradictions; `check_posting_liveness.py` parses explicit deadlines and gates expired postings.
- Candidate-side Bookface workflow: `scripts/bookface_mcp_auth.py` supports DCR token bootstrap, `--list-actions` and `--forget`; `SKILL.md` documents account-bound limits, the `yc` CLI fallback and verified dead ends for `search_jobs`/`company_jobs` and `finding-a-startup-job`.
- Two run modes are explicit: quick tailoring versus footprint enrichment. Anti-hypertailoring and keyword-mirroring gates keep exact posting vocabulary only where it is truthful and defensible.
- Cross-source job dedup, structured sourcing references, and a humane wording audit turn third-party repos into candidate-side evidence without importing employer-side workflows.

### Changed

- Provenance now uses the live GitHub PR summary (`106 authored`, `40 merged`, `22 external across 15 repos` as of 2026-11-21) and explicitly caveats self-reported Hugging Face model metrics.
- CV guide integration: 6–10 second scan, one primary role per application, 3–4 line summary, and Siemens-as-one-employer structure feed the tailoring flow.
- Tailored CVs are rendered from the latest candidate-approved baseline with official icons and verified layout/number gates.

### Fixed

- Knockout screening reads middle-dot city headers and rejects "A, B or C" lists as locations.
- Preflight timeout degradation, small-limit clamping and HF stack tokens in the bullet audit.
- Deadline expiry is authoritative even when a job form still returns HTTP 200; cover-letter HTML escaping no longer leaks literal `<` characters, and EU work-rights negation no longer false-flags.
- Candidate action parsing now targets only `waas_candidate`; employer tools containing "candidate" are ignored. Dedup handles `treg` `company_name`/`job_title` and `application_link` reindexing.

## [0.8.0] - 2026-11-18

### Added

- Canonical house-style renderer path: `scripts/render_sample.py --fields <json> --output <pdf> [--margin-mm N]` fills `template.html` through the same checked renderer as the public synthetic sample, so a tailored CV matches the approved baseline exactly (including uniform 15mm margins). Extracted `fill_template()` / `render_fields()` with unit tests for HTML escaping, the placeholder contract and the margin override.
- Privacy guard test (`tests/test_no_personal_data.py`): committed test/example fixtures must use reserved `example.*` email domains.

### Changed

- Removed candidate-specific job-application content from the public skill (a job-facts section for a specific EU tech role and named tailoring notes in SKILL.md) and fictionalized employer/project references in test fixtures. Tailored CVs and private sources stay out of version control; maintainer authorship and GitHub-noreply commit metadata are retained.

### Fixed

- Knockout screening now parses "N+ years <job-function list> experience" and treats "3+ years X OR 4+ years Y" as alternatives (the lower floor), instead of missing the requirement or stacking the branches.

## [0.7.0] - 2026-11-07

### Added

- Grounded fit scorer (`scripts/fit_score.py`, `docs/fit-scoring.md`, `examples/fit/`): per-requirement judgments on described levels are combined in code into a fit band with an uncertainty range. Evidence quotes are verified against approved sources and unverified high claims are capped; hard gates, coverage limits and experience arithmetic (overlapping roles counted once) never go to the judge. The judge is pluggable and no service is called.
- Number fact gate (`scripts/check_cv_numbers.py`): after rendering, fail delivery when a CV number is backed by none of the approved source files (foundation.md, provenance.md, or per-application sources via repeatable `--source`). Years, single digits and alphanumeric-identifier fragments are skipped; wiring documented in SKILL.md step 6. Inspired by career-ops' generate-pdf fact gate.
- Posting liveness gate (`scripts/check_posting_liveness.py`): before tailoring, classify a posting URL as live, dead or suspicious from the HTTP status, closure phrases, expected role title and redirect behavior; wiring documented in SKILL.md step 1 and `docs/delivery-checks.md`. Suspicious results require browser verification; the script cannot render JavaScript.

### Changed

- The bounded JSON loader moved into `scripts/cv_checks.py` and is shared by the structured builder and the fit scorer. Structured input now also rejects `NaN` and `Infinity`, and its error messages are worded generically.
- CV tailoring now uses the latest candidate-approved CV as the default design baseline across authoring paths; redesigns require approval. PDF checking can assert private section landmarks in extracted order without logging their text. Builder headings use strict line matching to avoid body-text false positives.
- Replaced the README's flat file listing with a directory tree and purpose table; clarified prerequisites, configuration, delivery checks and completed-roadmap status.
- Retired completed implementation plans while retaining the user guides, test coverage and regeneration inputs.

### Fixed

- CSS escape sequences could disguise `@import` and `url()` from the renderer's resource preflight. The checker now decodes CSS escapes before rejecting resource-loading tokens, with regression coverage for escaped identifiers, functions and local-file imports.
- The README workflow preview now has an opaque light background and explicit dark labels, independent of the surrounding theme. Added standalone preview regeneration and rendering regressions.
- The CI browser smoke check uses the renderer's bounded startup deadline instead of a shorter cold-start limit; PDF validation remains required.

## [0.6.0] - 2026-10-09

### Added

- Repeatable structured CV input and Engineering, Operations/Support, Research and Management ordering presets over one 10.5pt single-column layout.
- A4/Letter template gallery using fictional data; empty optional sections are omitted without fixed role slots or hidden content trimming.
- An animated export workflow and interactive public source map with three guided tours, compact mobile controls and regeneration helpers.
- Shared PDF delivery checks and automatic selected-posting overlap review before publishing a local render.
- Actual Chromium/Poppler failure-path tests on Linux and macOS, alongside the private corpus tests.
- Selected Obsidian Markdown imports with comment/embed/callout exclusions and conflicting-author protections.

### Fixed

- Handle macOS headless browsers that write a completed PDF but linger during shutdown, stopping only the owned render session before full PDF validation.
- Technical prose is no longer mistaken for CSS resource loading; layout-preserving extraction retains wrapped URL hyphens.
- Public diagram generation rejects forbidden tracked paths before reading content and stages all outputs before publication.
- Paper overrides no longer depend on one exact CSS string. Failed exports cannot replace an existing output; temporary browser profiles and HTML are cleaned up.
- Phrase reports show maximal runs and Unicode-aware metrics, omit private passages by default, and distinguish strict failure from review mode.

## [0.5.0] - 2026-10-09

### Added

- Private, opt-in writing corpus with local Markdown/Cabinet, Sanity export, original-record and author-filtered message imports.
- Descriptive voice references, optional private excerpts, draft comparison and author-scoped deletion. No model training or live provider connector is included.
- Source revision handling, duplicate-text suppression, private-output protections and synthetic CLI tests on Linux/macOS with Python 3.11 and 3.14.

### Changed

- Refined the landing page with a fictional document preview, readable typography, responsive navigation and explicit product limitations.
- Added glass-inspired navigation and convection-inspired ambient motion with a soft fade into the sample section. Each page load starts with a fresh random arrangement; the lower sections have no lava effect.
- Added independently levitating chalk-style icons to the reading sections only, with motion controls and reduced-motion support. The header and footer have no chalk icons; the footer has a static bottom glow.
- Improved paragraph alignment, shortened the desktop subtitle, and added accessible command highlighting.
- Added smooth native FAQ expansion with an instant reduced-motion fallback.
- Added an Appearance panel with persistent settings, explicit transparency opt-in, accessibility fallbacks and pausing when hidden or offscreen.
- Unified section spacing on a responsive scale: 96px between desktop sections and 64px on narrow screens.
- Replaced the website mockup with an actual rendered sample PDF and screenshot, with fictional public source data and a reproduction command. The wider viewer has readable-size and fit-page modes.
- Simplified the README license footer to the MIT link.
- Grouped README badges by host, local tool and optional service; removed the employer-specific footer disclaimer.
- Shared one logo asset across the website and banner source.
- Used an explicit root-skill path in the Claude plugin manifest instead of recursive or resource-breaking links.

### Fixed

- Keyboard navigation and selected-state semantics for installation and example tabs.
- Clipboard feedback and recovery when automatic copying is denied or unavailable.
- Installation instructions that incorrectly chained Claude session commands as shell commands.
- Public claims that overstated automated enforcement, ATS compatibility and exact voice matching.

## [0.4.0] - 2026-10-08

### Added

- No job-description mirroring gate: the posting informs emphasis and ordering only; CV wording stays in the candidate's voice.
- Candidate-voice rule: plain, specific, lightly warm; write-like-human discipline; voice-sample support planned.
- Private `provenance.md`: verification notes, external PR merge states, metrics bank, voice plan - separated from the master resume.
- Personal configuration section for portable paths (CV guide, applications log, output directory).
- ATS punctuation rules: no em/en dashes or smart quotes; plain hyphens in date ranges (documented top parsing failures).
- Deterministic banner: `assets/banner.html` rendered by headless Chrome; the wordmark is real type and cannot be misspelled.
- JD-overlap lint: `scripts/jd_overlap.py` flags CV phrasing shared with the posting.
- Claude Code plugin and marketplace manifests; Codex and AGENTS.md support.
- Repository renamed cv-forge → cv-witness (unique address); private history purged at publication.

## [0.3.1] - 2026-10-07

### Added

- Amazon Quick native-flow documentation, verified against a real session.
- Merge-state verification: external PRs are checked via the GitHub API before being cited.

## [0.3.0] - 2026-10-07

### Added

- Verified desktop and cross-platform evidence in the resume sources.
- Amazon Quick Desktop as the preferred authoring path.

### Fixed

- Bullet-marker clipping at the left edge.
- Vertical balance of the rendered page.

## [0.2.0] - 2026-10-06

### Added

- ATS checklist and mechanical output verification (pdftotext extraction, one-page assertion, placeholder scan).
- First end-to-end tailored CV produced with the skill (Logitech QA internship).

## [0.1.0] - 2026-09

### Added

- Initial skill: foundation-driven tailoring, single-column ATS-safe template, headless-Chrome renderer, anti-fabrication `[FILL: ...]` gate.
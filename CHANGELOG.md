# Changelog

All notable changes to cv-witness are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versioning follows
[Semantic Versioning](https://semver.org/). Versions before 0.4.0 were
developed in a private history that was purged when the repository went
public; their entries are consolidated summaries, not commit-for-commit notes.

## [Unreleased]

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
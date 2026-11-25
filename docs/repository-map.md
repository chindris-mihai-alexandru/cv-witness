# Repository map

This is the canonical inventory of the public repository layout. The README keeps a short orientation; this page carries the complete grouped list so the README does not become a stale file tree.

The filesystem is the source of truth. `tests/test_readme_structure.py` fails when a tracked script, root file, or reference area is missing here.

## Top level

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Agent workflow, evidence rules and delivery gates. |
| `AGENTS.md` | Short agent entry rules; points to `SKILL.md`. |
| `README.md` | Public overview, install, usage and links. |
| `CHANGELOG.md` | Shipped changes. |
| `CONTRIBUTING.md` | Contribution expectations. |
| `LICENSE` | MIT license. |
| `template.html` | Canonical approved house-style CV template. |
| `render.sh` | Checked-render shell entrypoint. |
| `index.html` | Static project website. |
| `.gitignore` | Excludes private sources and generated local files. |

## Directories

| Path | Purpose |
| --- | --- |
| `.claude-plugin/` | Claude Code plugin manifest. |
| `.github/workflows/` | Tests and GitHub Pages deployment. |
| `assets/` | Website image, sample CV and exploration previews. |
| `assets/explore/` | Interactive workflow, source map, guided tours and fictional PDF gallery. |
| `docs/` | Usage guides, contracts and this repository map. |
| `examples/` | Fictional CV fields and inputs. |
| `examples/fit/` | Fictional fit-scoring fixtures. |
| `references/` | Candidate-side rules and sourcing guidance. |
| `references/company_lists/` | Public company lists used by screening tools. |
| `scripts/` | Local tools, grouped below. |
| `templates/` | Repeatable structured CV template. |
| `tests/` | Synthetic contracts and real PDF regressions. |

`foundation.md`, `provenance.md` and tailored CVs are private and excluded by `.gitignore`.

## Scripts by purpose

| Purpose | Scripts |
| --- | --- |
| Render and build | `build_cv.py`, `render_cv.py`, `render_sample.py`, `render_exploration.py`, `render_template_gallery.py` |
| Delivery checks | `ats_text_export.py`, `ats_validate.py`, `bullet_audit.py`, `check_cv.py`, `check_cv_numbers.py`, `check_cv_titles.py`, `cover_letter_check.py`, `cv_checks.py`, `cv_layout.py`, `humane_audit.py`, `jd_coverage.py`, `jd_overlap.py`, `payload_lint.py`, `verify_layout.py` |
| Posting and role triage | `check_posting_liveness.py`, `posting_integrity.py`, `role_clarity.py`, `knockout_check.py`, `preflight.py`, `fit_score.py` |
| Company, network and compensation | `company_context.py`, `comp_data.py`, `trust_data.py`, `public_footprint.py`, `eu_network.py`, `yc_network.py` |
| Candidate evidence and interview prep | `linkedin_export_import.py`, `linkedin_profile_diff.py`, `star_worksheet.py`, `story_provenance.py`, `voice_corpus.py` |
| Optional integrations and metadata | `bookface_mcp_auth.py`, `rms_metadata.py`, `ci_pdf_smoke.py` |

## Related maps

- [Interactive source map](https://chindris-mihai-alexandru.github.io/cv-witness/assets/explore/codegraph.html)
- [Interactive workflow](https://chindris-mihai-alexandru.github.io/cv-witness/assets/explore/workflow.html)
- [Exploration regeneration and limits](exploration.md)

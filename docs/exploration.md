# Explore cv-witness

Date: 2026-10-09
POC: Mihai-Alexandru Chindriș
TL;DR: Use the animated workflow for approval and export boundaries, and the interactive source map for files, symbols and dependencies. Both run locally without accounts or API keys.

## Two views with different jobs

[Open project exploration](https://chindris-mihai-alexandru.github.io/cv-witness/assets/explore/).

- **Checked-export workflow:** follows approved wording through the shared layout, temporary PDF, delivery checks and publication. Failure preserves the prior output. Animation shows direction, not live activity.
- **Interactive source map:** searches public files and symbols and provides three guided reading tours. Import, containment and external-dependency edges come from a deterministic scan. Inferred call edges are disabled; dynamic or subprocess relationships may not appear.

The source map starts in the expandable explorer because this small repository has no cross-module import links worth showing in its overview. A separate workflow explains the actual export sequence; the map does not invent dependency edges to make that sequence appear.

Tour subjects are checked exports, private writing references, and the shared career-lane layout. Search brings matching files and symbols into the file drawer; selecting a result opens its description and dependency lists. Desktop readers can use the overview or star-map views as alternatives.

Use **Tab** for normal keyboard focus, **V** to change views, **P** for tours, and **Space** to pause map motion. Theme and pause controls are also buttons. Motion follows reduced-motion preferences. On phones, the Files drawer keeps controls out of the graph; the workflow scrolls sideways instead of shrinking labels below a readable size.

For a noninteractive reading order, use the exploration landing page or the contracts in `docs/`. The canvas map is a visual aid, not a substitute for those text guides.

## README and offline use

GitHub READMEs cannot execute an interactive HTML page. The static workflow preview has an opaque light background and explicit dark labels so it stays readable in either GitHub theme. It links to the interactive workflow, which retains its light/dark switch. The actual HTML artifacts are self-contained and can also be opened from a local clone:

```text
assets/explore/index.html
assets/explore/workflow.html
assets/explore/codegraph.html
```

The landing page links eight fictional A4/Letter template PDFs. A preview is not the application document; the linked PDFs contain live text and were exported through the shared checks.

Refresh only the README image from the existing checked workflow without installing the diagram plugins:

```sh
python3 scripts/render_exploration.py --preview-only
```

This changes the static preview only. It preserves the generated labels and connector geometry, removes motion and theme dependencies, and replaces the image only after conversion succeeds.

## Regenerate after source changes

Install the core diagram plugins on your machine, then pass their actual local directories:

```sh
python3 scripts/render_exploration.py \
  --codegraph-skill /absolute/path/to/codegraph \
  --glowmotion-skill /absolute/path/to/glowmotion
```

The helper exports a specific committed Git revision, scans that public snapshot with call inference disabled, applies the reviewed summaries and tours in `docs/exploration-enrichment.json`, and invokes the installed renderers.

Before reading file contents, it checks tracked tree metadata. Forbidden private paths, symlinks and submodules abort generation. The generated exploration tree is excluded from scanning so the map does not map itself. Untracked or ignored working files never enter the snapshot. Local root paths are removed from the published metadata; scanner-produced nodes and edges are unchanged.

The workflow's semantic graph lives in the helper; layout coordinates come from the diagram engine. Its geometry checker must report zero violations. Source-map IDs and enrichment are validated before publication. Project-specific adaptations keep keyboard focus and compact mobile controls usable without changing the installed plugins.

All generated diagrams are staged and checked before any existing output is replaced. Ordinary publication failures roll back the affected files. Regeneration does not claim to protect against a machine crash or concurrent edits to the asset directory.

Commit source changes before regenerating so the embedded revision corresponds to the scanned code. The helper intentionally ignores uncommitted implementation edits. Review summaries and tours after a scan; a structurally valid graph cannot establish that a prose description is correct.

## Privacy

No personal Cabinet or Obsidian vault, private resume, voice corpus, model account or provider API is used to build the public diagrams. Keep sensitive files untracked and out of `assets/`; GitHub Pages publishes that asset tree.

A Git snapshot is not a general secret scanner. Public tracked content still needs review before it is mapped or published.

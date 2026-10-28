# Repeatable CV templates

Date: 2026-10-09
POC: Mihai-Alexandru Chindriș
TL;DR: Supply approved structured wording, select a career lane and paper size, and export through one checked layout. Roles repeat without fixed slots or manual CSS adjustments.

## Build a CV

Python 3.11+, a Chromium-family browser and Poppler are required. Start with the [fictional structured example](../examples/structured-cv.json); keep real inputs outside public examples and assets.

```sh
python3 scripts/build_cv.py /absolute/path/to/approved-cv.json \
  "$HOME/Downloads/Candidate-CV-Company-Role.pdf" \
  --lane engineering --paper a4 --max-pages 1 \
  --posting /absolute/path/to/selected-posting.txt
```

The output is published only after the shared [delivery checks](delivery-checks.md) pass. `--posting` is optional; selecting it runs phrase review automatically. Strict overlap checks can match generic industry wording, so use `--overlap-policy review` only after deciding those matches need review rather than blocking.

Use `--paper letter` for US Letter. The default page limit is one; a longer resume or research CV needs an explicit approved limit such as `--max-pages 3`. Excess pages fail visibly. The builder never discards roles, cuts bullets, changes claims or reduces the body font to manufacture a pass.

Existing output is preserved unless `--replace` is requested. Failed rendering or checks preserve that output even with replacement enabled. Input documents are never modified.

## Version-1 input

The root JSON object accepts only these fields:

| Field | Shape | Behavior |
| --- | --- | --- |
| `schema_version` | Integer `1` | Required; unsupported versions fail. |
| `header` | Object | Required; `name` is required. Optional `role` and `contacts`. |
| `summary` | String | Optional; an empty string omits the section. |
| `skills` | List of objects | Each entry has `category` and `text`. |
| `experience` | List of employers | Each has `employer`, optional `location`, and a nonempty `roles` list. |
| `projects` | List of objects | Required `name` and nonempty `bullets`; optional `description`, `dates` and `url`. |
| `education` | List of strings | Approved qualification/institution/date wording. |
| `certifications` | List of strings | Approved certification wording. |
| `publications` | List of objects | Required `citation`, optional `url`. |
| `languages` | List of strings | Candidate-confirmed proficiency wording. |
| `note` | String | Optional source note; validated but not printed in the CV. |

Each contact has `label` and `value`, with an optional explicit HTTP(S), `mailto` or `tel` URL. Each role has `title`, `dates` and a nonempty list of bullet strings. Dates are supplied wording, not automatically inferred or checked against a career history.

```json
{
  "schema_version": 1,
  "header": {
    "name": "Alex Morgan",
    "contacts": [
      {"label": "Email", "value": "alex@example.com", "url": "mailto:alex@example.com"}
    ]
  },
  "experience": [
    {
      "employer": "Sample Studio (fictional)",
      "roles": [
        {
          "title": "Software Engineer",
          "dates": "2024 - Present",
          "bullets": ["Built a small reporting tool and documented its input checks."]
        }
      ]
    }
  ]
}
```

Add roles or employers by adding records, not numbered placeholders. Collections support up to 200 entries each; contacts are limited to 12. Text values have an 8,000-character limit and input files a 16 MiB limit. A very large CV may exceed the approved page limit even though its input is valid.

Empty optional lists produce no heading. Provide at least one nonempty section. Unknown fields, duplicate JSON keys, wrong types, empty required strings, unsafe link schemes, invalid Unicode and unresolved fill/template markers fail rather than disappearing silently. Supplied text is escaped before it enters the HTML.

## Four ordering presets

| `--lane` | Section order, omitting empty sections |
| --- | --- |
| `engineering` | Summary, Skills, Experience, Projects, Education, Certifications, Publications, Languages |
| `operations` | Summary, Experience, Skills, Certifications, Projects, Education, Publications, Languages |
| `research` | Summary, Education, Experience, Publications, Projects, Skills, Certifications, Languages |
| `management` | Summary, Experience, Projects, Skills, Education, Certifications, Publications, Languages |

Operations includes support roles. These are presentation defaults, not rules about what experience someone should claim. The same supplied content appears in every preset.

`--section-order` accepts comma-separated section keys. It must include every nonempty section exactly once; it cannot silently hide content. For an education-first example:

```sh
python3 scripts/build_cv.py approved.json output.pdf \
  --lane research --paper letter --max-pages 3 \
  --section-order education,experience,publications,skills
```

That command is valid only when those four sections are the complete nonempty set in the input. Add other nonempty keys explicitly or use the preset.

## Layout and verification

`templates/structured.html` supplies one single-column print layout. Body copy stays at 10.5pt, metadata remains inline, and contact links have visible text. Long experience blocks can split across pages; heading break controls reduce stranded headings without forcing an entire long section onto one page.

The builder supplies an expected-text contract derived from emitted wording and checks selected section headings in the lane's order after export. The shared checker verifies expected text, ordered landmarks, page geometry, live text, markers and selected-posting overlap. Tests also inspect section order and long-role content. Landmark checks detect missing or misordered strings in extracted text; they do not establish semantic headings, complete reading order, visual fidelity to a candidate's baseline, or parsing by a particular ATS. Compare every rendered page with the approved CV and verify the facts.

No local export can promise “100% ATS parsability” across hiring platforms. These checks reduce formatting risk; they do not certify parsing, ranking, originality or an interview.

All eight [fictional lane/paper samples](https://chindris-mihai-alexandru.github.io/cv-witness/assets/explore/) demonstrate the same approved example. Reproduce them with:

```sh
python3 scripts/render_template_gallery.py
```

The gallery helper always reads the tracked fictional fixture, never an arbitrary personal CV. Use `--output-dir` to reproduce outside the published asset tree.

## Compatibility

`template.html` remains the legacy manual layout. `render.sh` remains the checked HTML-to-PDF entrypoint. The structured builder delegates to that same Python renderer and validator; there are no four copied renderers or style systems.

Candidate approval, independent factual review and private-source handling remain defined by `SKILL.md`.

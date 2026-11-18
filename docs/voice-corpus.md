# Candidate voice references

Date: 2026-10-08
POC: Mihai-Alexandru Chindriș
TL;DR: Import selected original writing locally, inspect its descriptive signals, and give your agent an approved style reference. No model training, provider login, automatic upload, or exact-voice score is involved.

## What this feature does

`scripts/voice_corpus.py` reads approved writing into a private SQLite corpus. It produces a reference describing sentence lengths and their variance, paragraph length, punctuation, contractions, first-person language and a few descriptive markers. You can compare those signals with a text draft and review long shared passages without printing the passages.

The reference guides wording, not resume facts. A story about a project does not become verified CV experience just because it is in your writing corpus. Your verified resume sources, professional register and current preferences still take priority.

Python 3.11+ and the standard library are sufficient. Git is required only if you put private storage inside a checkout, because the tool verifies that it is untracked and ignored. Linux and macOS are covered by the synthetic test workflow.

## Choose originals before importing

Select writing you actually composed: a blog post, an essay, a personal note, or your own conversational messages. Check the complete text, including quotations and edits. `--attest-human` records your confirmation; it cannot detect who wrote an unlabelled passage.

Do not select agent-written notes, AI-edited rewrites, generated summaries, graph entities, retrieved facts, assistant messages, other people's prose, job postings or generated CVs. Explicit generated or unknown-authorship labels are excluded even when an import has been attested. Marked quote and code regions are removed, but unmarked quotations or generated content cannot be reliably detected.

Choose a language and, preferably, a consistent genre. The tool does not automatically identify language or turn casual chat into professional CV prose. English-specific signals are omitted for other declared languages; token and sentence counting remain approximate, particularly for scripts without spaces.

## Local Markdown, including Cabinet and Obsidian

[Cabinet](https://docs.runcabinet.com/concepts/cabinet-file-format/) stores knowledge pages as Markdown on disk. No Cabinet connector or account export is necessary for an ordinary selected `.md` file.

Cabinet also stores agent-written pages and memory. Its Git history can help you review a page, but a commit author does not prove human authorship of every sentence. Select exact files or a curated writing folder; do not import an entire Cabinet root. Hidden agent/job/history directories and symlinked folders are not followed. Linked Cabinet sources need an explicit non-symlinked original or a reviewed local copy.

[Obsidian vaults](https://obsidian.md/help/file-formats) also keep Markdown on disk. Import selected original `.md` notes with the same command. The importer skips hidden configuration folders, ignores Canvas/Bases files, removes `%% comments %%`, embeds and quoted callouts, and preserves wiki-link display words without following their targets. Graph relations and file location do not prove authorship. Multiple or conflicting author properties are excluded; normalize complex metadata into the original-record format. No personal vault is scanned automatically.

First inspect the proposed import:

```sh
python3 scripts/voice_corpus.py import /absolute/path/to/approved-writing \
  --format text --author my-author-id --language en --genre blog \
  --attest-human --dry-run
```

Repeat without `--dry-run` after checking the accepted/excluded counts. A directory includes its direct `.md` and `.txt` files; add `--recursive` only when you intend to include child directories. Originals are not modified.

Optional simple front matter can declare `author_id`, `authorship`, `content_kind`, `language` and `genre`. Unknown or contradictory author labels are excluded. Complex YAML authorship structures should be normalized into the original-record format instead of relying on this deliberately small front-matter reader.

## Sanity posts

Use a local [Sanity dataset export](https://www.sanity.io/docs/content-lake/exporting-data), not a site scrape or generated content-agent response. The native importer accepts JSON, JSONL/NDJSON, or the official `.tar.gz` archive containing `data.ndjson`. Use Sanity's `--no-assets` and `--no-drafts` export options where appropriate; large asset archives may exceed the safety limits.

Sanity schemas differ. Specify the actual document type, body field and author field. Author references use their `_ref` value, not the author's display name. The namespace identifies the project and dataset so two datasets cannot silently share source identities.

```sh
python3 scripts/voice_corpus.py import /absolute/path/to/blog-export.tar.gz \
  --format sanity --namespace my-project/production \
  --document-type post --text-field body --author-field author \
  --author author-document-id --language en --genre blog \
  --attest-human --dry-run
```

`--text-field` and `--author-field` support dotted object paths such as `article.body` and `editorial.writer`. Missing, unknown or multiple authors are excluded. Published documents are selected by default; `drafts.` IDs require `--include-drafts`, and `versions.` IDs are excluded.

[Portable Text](https://www.portabletext.org/specification/) normal blocks retain ordered span text, including link anchor words. Headings, blockquotes, code spans and custom non-text objects are excluded from the prose measurements. The corpus keeps the selected field's extracted text and its document/field identity; it is not a complete Sanity document backup. Preserve your original export if you need its full block structure or metadata.

If a document has `authorship` or `content_kind` labels indicating generated content, the importer excludes it. If your schema lacks those labels, your selection and attestation remain the authorship boundary. The importer does not log into Sanity or fetch unpublished content.

## Other CMS and memory exports

A common envelope avoids duplicating provider-specific clients. It works for reviewed originals from another CMS, a mind-map tool or a memory system only when the original wording and author scope are preserved. It is not a native-format promise for every provider.

```json
{
  "schema_version": 1,
  "source_system": "cms-export",
  "source_namespace": "my-selected-dataset",
  "source_id": "original-document-123",
  "author_id": "my-author-id",
  "content_kind": "original",
  "authorship": "user_attested_original",
  "speaker_role": "author",
  "language": "en",
  "genre": "blog",
  "status": "published",
  "truncated": false,
  "updated_at": "2026-10-08T12:00:00Z",
  "text": "The complete original prose selected and reviewed by its author."
}
```

Use a JSON array or one object per JSONL/NDJSON line. `source_id` should be the stable original document identity, not a new retrieval-result ID on every run.

```sh
python3 scripts/voice_corpus.py import /absolute/path/to/originals.jsonl \
  --format records --namespace my-selected-dataset \
  --author my-author-id --language en --genre blog \
  --attest-human --dry-run
```

Provider distinctions matter:

- **Cognee:** [CHUNKS](https://docs.cognee.ai/python-api/search) can return source passages; summaries, completion answers and graph representations are derived. Prefer the original input document. A selected chunk still needs complete, reviewed text and author provenance.
- **Hindsight:** [recall](https://hindsight.vectorize.io/developer/api/recall) may include source chunks, while facts and observations are derived. Retrieval chunks can be truncated or incomplete; use originals retained outside the memory system rather than assuming a recall result is a full writing sample.
- **Mem0:** [raw message ingestion](https://docs.mem0.ai/api-reference/memory/add-memories) can preserve message content with `infer: false`. Ordinary inferred memories are not authored prose.
- **Zep/Graphiti, Letta, Supermemory and other stores:** normalize only a reviewed original document/message with preserved author and source scope. A graph, memory block, generated answer or summary is not an acceptable substitute.

Agent Memory Benchmark results evaluate memory and retrieval behavior. They are not a writing corpus, do not establish voice fidelity, and are not imported automatically. Provider rankings are irrelevant to whether a sample contains your original wording.

## Author-filtered messages

Use `--format messages` with an envelope containing `schema_version`, `source_system`, `source_namespace`, `source_id`, `content_kind: "original"`, `authorship: "user_attested_original"` and a `messages` array. Each selected message must have `role: "user"`, the exact `author_id`, and string `content`.

Assistant/system turns and other authors are excluded before storage. Wrapper and message generated labels, draft status and truncation are checked. The conversation is a separate genre, not silently mixed into blog prose. This normalized format is not a direct importer for every vendor's chat-export schema.

## Generate a reference and compare a draft

Inspect your admitted sources:

```sh
python3 scripts/voice_corpus.py status --author my-author-id
```

Generate a private reference:

```sh
python3 scripts/voice_corpus.py profile \
  --author my-author-id --language en --genre blog \
  --output "$HOME/.cv-witness/voice/reference.md"
```

Without `--output`, only aggregate signals and limitations print. Excerpts are absent by default. Add `--include-excerpts` only when you explicitly want a few short source passages in the private file. If an agent reads that reference, its model provider's data policy applies; the local importer itself makes no network or model calls.

`--replace` regenerates only a recognized profile for the same author and language. It refuses imported sources, other authors' references and unrelated files. Generated profiles are marked as generated so they cannot become new writing samples on re-import.

```sh
python3 scripts/voice_corpus.py compare /absolute/path/to/draft.md \
  --author my-author-id --language en --genre blog
```

Comparison reports descriptive differences and the count of shared eight-word runs, not a pass/fail or accuracy score. Sentence-length and tone-marker measures depend on topic and genre. The English passive-pattern estimate is deliberately labelled a heuristic; it is not a validated active-verb ratio.

The tool warns when the corpus is small. Several substantial, relevant originals are more useful than one short post or a large mixed collection. The warning threshold is a conservative product choice, not scientific proof of corpus sufficiency.

## Storage, updates and deletion

Storage defaults to `~/.cv-witness/voice`, outside the checkout. POSIX directories/files require owner-only permissions: 0700/0600. This is not encryption; secure the device and backups separately.

`--store` can point elsewhere. Inside a Git checkout, only `.voice/` or `voice-corpus/` is allowed, and the exact destination must be untracked and ignored by Git. Never put corpus data or references into `assets/`, public examples or CI artifacts. Symlinked paths are rejected; use canonical paths on systems with aliases such as macOS `/tmp`.

Re-importing the same source is idempotent; changed originals update their matching identity. Dated sources are protected against older or undated replacements, and conflicting content at the same timestamp aborts the batch. Exact duplicate prose contributes once to a profile while each source retains its provenance.

Imports are upserts, not complete synchronizations. If a source disappears from an export or later becomes ineligible, its previously admitted copy remains until you delete it. Review `status`, delete unwanted sources, and regenerate references after any change.

```sh
python3 scripts/voice_corpus.py delete --author my-author-id --confirm
```

Add `--source-key` from `status` to delete one sample. Deletion preserves originals and other authors. Previously exported references, backups and filesystem snapshots are not deleted by the tool.

## Technical verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

The synthetic-only suite covers imports, authorship/role filters, drafts/truncation, quoted/generated material, Unicode, malformed JSON, archive traversal/expansion, source preservation, revisions, private permissions, Git-ignore checks, profile replacement, comparison, deletion and a clean-checkout command workflow. It uses no personal Cabinet, Sanity or memory-account data.

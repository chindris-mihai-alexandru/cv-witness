# Voice corpus implementation plan

Date: 2026-10-08
POC: cv-witness contributors
Issue: #3
TL;DR: Import selected originals locally, retain their provenance, and produce a cautious writing-style reference. No model training, automatic uploads, or exact-voice claims.

## Technical scope

1. One private corpus format shared by Markdown/Cabinet exports, Sanity exports, and original-source records from memory services.
2. Native local text/Markdown, Sanity NDJSON or export archive, and role-filtered message imports. A strict original-record envelope handles Cognee, Hindsight, Mem0, Zep/Graphiti, Letta, Supermemory, other CMS tools, and future sources without provider SDKs.
3. Explicit author selection and confirmation that samples are human-written originals. Reject derived facts, summaries, assistant/system messages, benchmark material, unknown authors, and conflicting source identities.
4. Keep source documents unchanged. Store admitted text and origin in a private local SQLite corpus; upsert revisions and deduplicate text for profiling.
5. Separate source facts from style. Measure sentence-length distribution/variance, paragraph lengths, contractions, first-person language, punctuation and descriptive markers. Label grammar/passive estimates as heuristics; do not invent an active-verb accuracy score.
6. Profiles must expose sample size and limitations. Keep different languages separate; allow genre selection and optional, explicitly requested source excerpts for agent reference.
7. Dry run, status, profile/export, and delete commands. No full passages on stdout by default. Local export ingestion must never authenticate to or mutate a provider.

## Privacy and failure cases

- Default storage is outside the checkout. A private `.voice/` location in the skill is gitignored before any corpus data is written.
- No real Cabinet notes, Sanity account, private master resume, or user corpus is read while developing. Tests use synthetic originals.
- Bound input sizes and archive members. Do not extract archive paths or follow source symlinks. Decode UTF-8 strictly.
- Malformed input aborts without partial corpus updates. Unknown/mixed/derived records are excluded with metadata-only counts.
- SQLite transactions protect imports; private-directory and file permissions protect local artifacts. Never overwrite source files or publish private profiles.
- Consent is an attestation, not automated authorship or AI detection. Provider claims and retrieval benchmarks do not establish originality.

## Verification

Use standard-library unittest with synthetic text, Portable Text, memory records and chat exports. Cover published/draft/version filtering, multi-author sources, quoted/code blocks, Unicode, duplicate/revised records, archive traversal, malformed exports, atomic imports, storage restrictions, empty/small/mixed-language corpora, permission errors, excerpt opt-in, deletion, and end-to-end CLI operation.

Verified: 79 synthetic tests pass locally on Python 3.11 and 3.14. Both push and PR workflows passed all four Linux/macOS runtime combinations at technical commit `16f3b94`. The clean-checkout test exercises import, private profile generation, comparison and deletion from another working directory.

Review findings were fixed with regressions: source/profile overwrite, cross-author replacement, undated/older revisions, generated Sanity content, draft/truncated messages, malformed quotation markup, invalid Unicode, archive expansion including PAX metadata, private permissions and tracked/unignored storage. No real writing or account data was used.

## After the technical bar passes

Update skill instructions, repository map, README, and website to describe supported local imports honestly. Keep live-provider connectors and benchmark integrations separate from this feature. Mark #3 complete only after executable tests and a clean-checkout smoke test pass.

## Research constraints

Sanity has schema-specific author fields and Portable Text originals. Hindsight observations, Cognee graph summaries, and many memory-provider results are generated representations. Their source originals can be admitted only when text and author provenance are explicitly preserved. Agent Memory Benchmark evaluates memory/retrieval systems; its evaluation datasets are not a candidate voice corpus.

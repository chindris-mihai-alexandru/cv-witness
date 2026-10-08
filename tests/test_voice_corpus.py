"""Synthetic-only tests; no account, network, or personal corpus access."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import voice_corpus as voice

PROSE = "I built a small garden planner because my notes were scattered. It keeps the watering schedule simple, and I can change a task without opening another app. I usually explain the tradeoffs in a short note."
OTHER = "We tried a different route through the park this morning. The path was quieter than expected, although the signs were missing near the bridge. I wrote down what changed so the next walk would be easier to plan."
SECRET = "QUOTED_OR_ASSISTANT_SENTINEL"


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cv-witness-test-")
        self.root = Path(self.temporary.name).resolve()
        self.store = self.root / "private"
        self.script = Path(voice.__file__).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def export(self, name, records):
        return self.write(name, json.dumps(records, ensure_ascii=True))

    def args(self, *arguments):
        return voice.parser().parse_args([*arguments, "--store", str(self.store), "--author", "alex"])

    def import_text(self, text=PROSE, name="sample.md", *extra):
        path = self.write(name, text)
        args = self.args("import", str(path), "--format", "text", "--attest-human", *extra)
        return voice.execute(args)

    def envelope(self, **changes):
        record = {"schema_version": 1, "source_id": "post-1", "source_system": "cognee", "source_namespace": "personal", "author_id": "alex", "content_kind": "original", "authorship": "user_attested_original", "text": PROSE, "language": "en", "genre": "blog", "status": "published", "updated_at": "2026-10-01T12:00:00Z"}
        record.update(changes)
        return record

    def import_records(self, records, name="originals.json", *extra):
        path = self.export(name, records)
        return voice.execute(self.args("import", str(path), "--format", "records", "--namespace", "personal", "--attest-human", *extra))

    def sanity(self, **changes):
        doc = {"_id": "post-1", "_type": "post", "author": {"_type": "reference", "_ref": "alex"}, "_updatedAt": "2026-10-01T12:00:00Z", "body": [{"_type": "block", "_key": "a", "style": "normal", "children": [{"_type": "span", "text": PROSE, "marks": []}], "markDefs": []}]}
        doc.update(changes)
        return doc

    def import_sanity(self, docs, *extra):
        path = self.export("sanity.json", docs)
        return voice.execute(self.args("import", str(path), "--format", "sanity", "--namespace", "project/blog", "--attest-human", *extra))

    def profile(self, *extra):
        return voice.execute(self.args("profile", "--language", "en", *extra))

    def test_attestation_is_required_even_on_dry_run(self):
        path = self.write("sample.md", PROSE)
        with self.assertRaises(voice.CorpusError):
            voice.execute(self.args("import", str(path), "--format", "text", "--dry-run"))
        self.assertFalse(self.store.exists())

    def test_dry_run_changes_neither_inputs_nor_store(self):
        result = self.import_text(PROSE, "sample.md", "--dry-run")
        self.assertEqual(result["accepted_records"], 1)
        self.assertFalse(self.store.exists())
        self.assertEqual((self.root / "sample.md").read_text(), PROSE)

    def test_plain_import_profile_is_local_and_passage_free(self):
        result = self.import_text()
        self.assertEqual(result["storage_changes"], {"added": 1})
        profile = self.profile()
        self.assertEqual(profile["distinct_samples"], 1)
        self.assertGreater(profile["metrics"]["words"], 20)
        self.assertNotIn(PROSE, json.dumps(profile))
        self.assertNotIn("sources", profile)
        self.assertTrue(any("Small corpus" in warning for warning in profile["warnings"]))

    def test_identical_reimport_is_idempotent(self):
        self.import_text()
        result = self.import_text()
        self.assertEqual(result["storage_changes"], {"unchanged": 1})
        self.assertEqual(self.profile()["source_records"], 1)

    def test_revision_updates_one_source(self):
        self.import_text()
        result = self.import_text(OTHER)
        self.assertEqual(result["storage_changes"], {"updated": 1})
        self.assertEqual(self.profile()["source_records"], 1)

    def test_duplicate_prose_across_sources_is_profiled_once(self):
        self.import_text()
        self.import_text(PROSE, "copy.md")
        profile = self.profile()
        self.assertEqual(profile["source_records"], 2)
        self.assertEqual(profile["distinct_samples"], 1)

    def test_markdown_drops_frontmatter_code_quotes_and_images(self):
        raw = "---\nauthor_id: alex\n---\n# Heading\n\n" + PROSE + "\n\n> " + SECRET + "\n\n```python\n" + SECRET + "\n```\n\n![" + SECRET + "](example.png)\n\n[Human anchor](https://example.com) stays."
        cleaned = voice.clean_prose(raw)
        self.assertNotIn(SECRET, cleaned)
        self.assertNotIn("Heading", cleaned)
        self.assertIn("Human anchor stays.", cleaned)
        self.assertNotIn("https://", cleaned)

    def test_html_drops_generated_or_quoted_containers(self):
        raw = "<p>" + PROSE + "</p><blockquote>" + SECRET + "</blockquote><pre><code>" + SECRET + "</code></pre><script>" + SECRET + "</script><p>" + OTHER + "</p>"
        cleaned = voice.clean_prose(raw)
        self.assertNotIn(SECRET, cleaned)
        self.assertIn(PROSE, cleaned)
        self.assertIn(OTHER, cleaned)

    def test_frontmatter_other_author_or_generated_is_excluded(self):
        for metadata in ("author_id: bob", "authorship: ai_generated", "content_kind: summary"):
            with self.subTest(metadata=metadata):
                result = self.import_text("---\n" + metadata + "\n---\n" + PROSE)
                self.assertEqual(result["accepted_records"], 0)
        self.assertFalse(self.store.exists())

    def test_unclosed_frontmatter_fails_without_writing(self):
        with self.assertRaises(voice.CorpusError):
            self.import_text("---\nauthor_id: alex\n" + PROSE)
        self.assertFalse(self.store.exists())

    def test_short_and_code_only_samples_do_not_create_store(self):
        for text in ("A short sentence.", "```\n" + PROSE + "\n```", ""):
            result = self.import_text(text)
            self.assertEqual(result["accepted_records"], 0)
        self.assertFalse(self.store.exists())

    def test_utf8_bom_and_diacritics_are_preserved(self):
        text = "\ufeff" + PROSE + "\n\nȘtefan keeps a café notebook, and naïve ideas are welcome."
        self.import_text(text)
        rows, _ = voice.select_samples(self.store, "alex")
        self.assertIn("Ștefan", rows[0]["prose"])
        self.assertNotIn("\ufeff", rows[0]["prose"])

    def test_non_utf8_fails_closed(self):
        path = self.root / "binary.md"
        path.write_bytes(b"\xff\xfe\x00")
        with self.assertRaises(voice.CorpusError):
            voice.execute(self.args("import", str(path), "--format", "text", "--attest-human"))
        self.assertFalse(self.store.exists())

    def test_recursive_selection_is_explicit(self):
        directory = self.root / "notes"
        self.write("notes/first.md", PROSE)
        self.write("notes/deeper/second.md", OTHER)
        args = self.args("import", str(directory), "--format", "text", "--attest-human", "--dry-run")
        self.assertEqual(voice.execute(args)["accepted_records"], 1)
        args.recursive = True
        self.assertEqual(voice.execute(args)["accepted_records"], 2)

    def test_hidden_and_symlinked_files_are_not_traversed(self):
        self.write("notes/first.md", PROSE)
        self.write("notes/.secret/hidden.md", OTHER)
        linked = self.root / "notes" / "linked.md"
        linked.symlink_to(self.root / "notes" / "first.md")
        result = voice.execute(self.args("import", str(self.root / "notes"), "--format", "text", "--recursive", "--attest-human", "--dry-run"))
        self.assertEqual(result["accepted_records"], 1)
        with self.assertRaises(voice.CorpusError):
            voice.execute(self.args("import", str(linked), "--format", "text", "--attest-human"))

    def test_sanity_filters_author_drafts_versions_and_schema_type(self):
        docs = [self.sanity(), self.sanity(_id="drafts.post-1"), self.sanity(_id="versions.release.post-1"), self.sanity(_id="post-2", author={"_ref": "bob"}), self.sanity(_id="asset-1", _type="sanity.imageAsset"), self.sanity(_id="post-3", author=None)]
        result = self.import_sanity(docs)
        self.assertEqual(result["accepted_records"], 1)
        self.assertEqual(result["excluded"]["draft"], 1)
        self.assertEqual(result["excluded"]["version"], 1)
        self.assertEqual(result["excluded"]["other_or_unknown_author"], 2)

    def test_sanity_mixed_author_is_not_assigned_to_one_person(self):
        result = self.import_sanity([self.sanity(author=[{"_ref": "alex"}, {"_ref": "bob"}])])
        self.assertEqual(result["accepted_records"], 0)

    def test_sanity_allows_explicit_draft_selection(self):
        result = self.import_sanity([self.sanity(_id="drafts.post-1")], "--include-drafts")
        self.assertEqual(result["accepted_records"], 1)
        rows, _ = voice.select_samples(self.store, "alex")
        self.assertEqual(rows[0]["status"], "draft")

    def test_sanity_custom_author_and_body_paths(self):
        doc = self.sanity(editorial={"writer": {"_ref": "alex"}}, article={"content": PROSE})
        doc.pop("author")
        doc.pop("body")
        result = self.import_sanity([doc], "--author-field", "editorial.writer", "--text-field", "article.content")
        self.assertEqual(result["accepted_records"], 1)

    def test_portable_text_retains_link_anchors_and_skips_quotes(self):
        body = self.sanity()["body"]
        body[0]["children"] += [{"_type": "span", "text": " Human link anchor.", "marks": ["link-1"]}]
        body[0]["markDefs"] = [{"_key": "link-1", "_type": "link", "href": "https://example.com"}]
        body.append({"_type": "block", "style": "blockquote", "children": [{"_type": "span", "text": SECRET}]})
        body.append({"_type": "image", "caption": SECRET})
        body[0]["children"].append({"_type": "span", "text": SECRET, "marks": ["code"]})
        prose = voice.portable_text(body)
        self.assertIn("Human link anchor.", prose)
        self.assertNotIn(SECRET, prose)
        self.assertNotIn("https://", prose)

    def test_archive_import_reads_data_member_without_extracting(self):
        archive = self.root / "sanity.tar.gz"
        content = (json.dumps(self.sanity()) + "\n").encode()
        with tarfile.open(archive, "w:gz") as output:
            member = tarfile.TarInfo("data.ndjson")
            member.size = len(content)
            output.addfile(member, io.BytesIO(content))
        result = voice.execute(self.args("import", str(archive), "--format", "sanity", "--namespace", "project/blog", "--attest-human"))
        self.assertEqual(result["accepted_records"], 1)
        self.assertFalse((self.root / "data.ndjson").exists())

    def test_archive_traversal_is_rejected(self):
        archive = self.root / "bad.tar"
        with tarfile.open(archive, "w") as output:
            member = tarfile.TarInfo("../data.ndjson")
            member.size = 2
            output.addfile(member, io.BytesIO(b"{}"))
        with self.assertRaises(voice.CorpusError):
            voice.sanity_archive(archive)

    def test_records_admit_only_exact_author_namespace_and_original(self):
        records = [self.envelope(), self.envelope(source_id="b", author_id="bob"), self.envelope(source_id="c", source_namespace="company"), self.envelope(source_id="d", content_kind="summary"), self.envelope(source_id="e", authorship="unknown"), self.envelope(source_id="f", speaker_role="assistant"), self.envelope(source_id="g", truncated=True)]
        result = self.import_records(records)
        self.assertEqual(result["accepted_records"], 1)
        self.assertEqual(sum(result["excluded"].values()), 6)

    def test_memory_provider_names_do_not_make_summaries_original(self):
        for provider in ("hindsight", "cognee", "mem0", "zep", "letta", "supermemory"):
            with self.subTest(provider=provider):
                result = self.import_records([self.envelope(source_system=provider, content_kind="observation")])
                self.assertEqual(result["accepted_records"], 0)

    def test_raw_provider_result_is_not_auto_attested(self):
        with self.assertRaises(voice.CorpusError):
            self.import_records([{"memory": PROSE, "user_id": "alex"}])
        self.assertFalse(self.store.exists())

    def test_structured_namespace_is_required(self):
        path = self.export("record.json", [self.envelope()])
        with self.assertRaises(voice.CorpusError):
            voice.execute(self.args("import", str(path), "--format", "records", "--attest-human"))

    def test_message_roles_are_selected_before_profiling(self):
        record = self.envelope(source_id="chat-1", messages=[{"role": "user", "author_id": "alex", "content": PROSE}, {"role": "assistant", "author_id": "alex", "content": SECRET}, {"role": "user", "author_id": "bob", "content": SECRET}])
        path = self.export("messages.json", [record])
        result = voice.execute(self.args("import", str(path), "--format", "messages", "--namespace", "personal", "--attest-human"))
        self.assertEqual(result["accepted_records"], 1)
        rows, _ = voice.select_samples(self.store, "alex")
        self.assertNotIn(SECRET, rows[0]["raw"])
        self.assertEqual(rows[0]["genre"], "conversation")

    def test_malformed_record_aborts_whole_import(self):
        path = self.write("bad.ndjson", json.dumps(self.envelope()) + "\n{broken\n")
        with self.assertRaises(voice.CorpusError):
            voice.execute(self.args("import", str(path), "--format", "records", "--namespace", "personal", "--attest-human"))
        self.assertFalse(self.store.exists())

    def test_conflicting_source_revisions_in_one_batch_abort(self):
        with self.assertRaises(voice.CorpusError):
            self.import_records([self.envelope(), self.envelope(text=OTHER)])
        self.assertFalse(self.store.exists())

    def test_older_revision_cannot_replace_newer_text(self):
        self.import_records([self.envelope(updated_at="2026-10-02T00:00:00Z")])
        result = self.import_records([self.envelope(text=OTHER, updated_at="2026-10-01T00:00:00Z")])
        self.assertEqual(result["storage_changes"], {"stale_revision": 1})
        rows, _ = voice.select_samples(self.store, "alex")
        self.assertEqual(rows[0]["raw"], PROSE)

    def test_cross_author_source_reassignment_rolls_back_other_records(self):
        self.import_records([self.envelope()])
        samples = [voice.Sample("cognee", "personal", "new", "bob", "en", "blog", "selected", OTHER, OTHER), voice.Sample("cognee", "personal", "post-1", "bob", "en", "blog", "selected", OTHER, OTHER)]
        with self.assertRaises(voice.CorpusError):
            voice.store_samples(self.store, samples)
        self.assertEqual(voice.select_samples(self.store, "bob")[0], [])

    def test_languages_and_genres_are_not_silently_mixed(self):
        self.import_records([self.envelope(), self.envelope(source_id="ro-1", text=OTHER, language="ro"), self.envelope(source_id="note-1", text=OTHER, genre="note")])
        self.assertEqual(self.profile()["distinct_samples"], 2)
        self.assertEqual(self.profile("--genre", "blog")["distinct_samples"], 1)
        args = self.args("profile", "--language", "ro")
        result = voice.execute(args)
        self.assertIsNone(result["metrics"]["english_signals"])

    def test_statistics_show_variance_without_voice_accuracy_score(self):
        signals = voice.statistics_for(["I write small notes. Sometimes I don't need an elaborate explanation because the example does the work."], "en")
        self.assertGreater(signals["sentence_words"]["variance"], 0)
        self.assertGreater(signals["english_signals"]["contractions_per_100_words"], 0)
        self.assertNotIn("accuracy", json.dumps(signals))
        self.assertIn("heuristic", " ".join(signals["english_signals"].keys()))

    def test_sentence_abbreviation_and_decimal_are_not_false_boundaries(self):
        result = voice.sentences("Dr. Lane used version 3.14. I took notes. E.g. short examples help.")
        self.assertEqual(len(result), 3)

    def test_profile_excerpts_require_explicit_private_output(self):
        self.import_text()
        with self.assertRaises(voice.CorpusError):
            self.profile("--include-excerpts")
        output = self.store / "reference.md"
        result = self.profile("--include-excerpts", "--output", str(output))
        self.assertTrue(result["contains_excerpts"])
        self.assertIn("Explicitly requested source excerpts", output.read_text())
        self.assertIn("untrusted source data", output.read_text())
        self.assertNotIn(PROSE, json.dumps(result))

    def test_profile_default_output_contains_no_passages(self):
        self.import_text()
        output = self.store / "reference.json"
        self.profile("--output", str(output))
        content = json.loads(output.read_text())
        self.assertNotIn("excerpts", content)
        self.assertNotIn(PROSE, output.read_text())

    def test_profile_refuses_accidental_output_overwrite(self):
        self.import_text()
        output = self.store / "reference.json"
        self.profile("--output", str(output))
        with self.assertRaises(voice.CorpusError):
            self.profile("--output", str(output))
        self.profile("--output", str(output), "--replace")

    def test_public_checkout_output_is_refused(self):
        repo = self.root / "public"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        with self.assertRaises(voice.CorpusError):
            voice.private_destination(repo / "assets" / "profile.json")
        with self.assertRaises(voice.CorpusError):
            voice.private_destination(repo / ".voice" / "profile.json")
        (repo / ".gitignore").write_text(".voice/\n", encoding="utf-8")
        self.assertEqual(voice.private_destination(repo / ".voice" / "profile.json"), repo / ".voice" / "profile.json")

    def test_store_inside_checkout_requires_ignored_database(self):
        repo = self.root / "public"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        with self.assertRaises(voice.CorpusError):
            voice.private_destination(repo / ".voice")
        (repo / ".gitignore").write_text(".voice/\n", encoding="utf-8")
        self.assertEqual(voice.private_destination(repo / ".voice"), repo / ".voice")

    def test_tracked_profile_is_refused_even_when_ignore_rule_exists(self):
        repo = self.root / "public"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        destination = repo / ".voice" / "profile.md"
        destination.parent.mkdir()
        destination.write_text("Public file", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", ".voice/profile.md"], check=True)
        (repo / ".gitignore").write_text(".voice/\n", encoding="utf-8")
        with self.assertRaises(voice.CorpusError):
            voice.private_destination(destination)

    def test_store_cannot_be_a_file_or_symbolic_link(self):
        file = self.write("file.md", PROSE)
        with self.assertRaises(voice.CorpusError):
            voice.ensure_store(file)
        link = self.root / "linked-store"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(voice.CorpusError):
            voice.ensure_store(link)

    @unittest.skipUnless(os.name == "posix", "POSIX permission check")
    def test_private_store_and_profiles_have_owner_only_permissions(self):
        self.import_text()
        self.profile("--output", str(self.store / "reference.md"))
        self.assertEqual(self.store.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.store / "corpus.sqlite3").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.store / "reference.md").stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(os.name == "posix", "POSIX permission check")
    def test_publicly_readable_store_is_rejected(self):
        self.store.mkdir(mode=0o755)
        with self.assertRaises(voice.CorpusError):
            self.import_text()

    def test_missing_corpus_status_does_not_create_storage(self):
        with self.assertRaises(voice.CorpusError):
            voice.execute(self.args("status"))
        self.assertFalse(self.store.exists())

    def test_comparison_reports_signals_and_copy_risk_not_passages(self):
        self.import_text()
        draft = self.write("draft.md", PROSE)
        result = voice.execute(self.args("compare", str(draft), "--language", "en"))
        self.assertGreater(result["shared_8_word_runs"], 0)
        self.assertEqual(result["purpose"], "descriptive_review_not_a_score")
        self.assertNotIn(PROSE, json.dumps(result))

    def test_delete_requires_confirmation_and_preserves_source(self):
        self.import_text()
        with self.assertRaises(voice.CorpusError):
            voice.execute(self.args("delete"))
        result = voice.execute(self.args("delete", "--confirm"))
        self.assertEqual(result["deleted_records"], 1)
        self.assertEqual(voice.execute(self.args("status"))["source_records"], 0)
        self.assertEqual((self.root / "sample.md").read_text(), PROSE)

    def test_delete_never_crosses_author_boundary(self):
        self.import_text()
        args = voice.parser().parse_args(["delete", "--store", str(self.store), "--author", "bob", "--confirm"])
        self.assertEqual(voice.execute(args)["deleted_records"], 0)
        self.assertEqual(self.profile()["distinct_samples"], 1)

    def test_real_cli_import_profile_compare_delete(self):
        sample = self.write("original.md", PROSE)
        base = [sys.executable, str(self.script)]
        common = ["--store", str(self.store), "--author", "alex"]
        commands = [["import", str(sample), "--format", "text", "--attest-human"], ["status"], ["profile", "--language", "en"], ["compare", str(sample), "--language", "en"], ["delete", "--confirm"]]
        for command in commands:
            with self.subTest(command=command[0]):
                result = subprocess.run(base + command + common, capture_output=True, text=True, timeout=10, cwd=self.root)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsInstance(json.loads(result.stdout), dict)
                self.assertNotIn(PROSE, result.stdout + result.stderr)

    def test_cli_errors_do_not_echo_input_or_traceback(self):
        path = self.write("malformed.json", '{"text": "' + SECRET)
        result = subprocess.run([sys.executable, str(self.script), "import", str(path), "--format", "records", "--namespace", "personal", "--author", "alex", "--attest-human", "--store", str(self.store)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_inline_html_quotes_are_not_voice_samples(self):
        text = PROSE + " <q>" + SECRET + "</q> " + OTHER
        self.assertNotIn(SECRET, voice.clean_prose(text))
        self.assertIn(OTHER, voice.clean_prose(text))

    def test_archive_limits_total_decompressed_members(self):
        archive = self.root / "large.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            member = tarfile.TarInfo("assets/padding.bin")
            member.size = 2048
            output.addfile(member, io.BytesIO(b"x" * 2048))
            data = json.dumps(self.sanity()).encode()
            member = tarfile.TarInfo("data.ndjson")
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))
        from unittest.mock import patch
        with patch.object(voice, "MAX_ARCHIVE_BYTES", 1024, create=True):
            with self.assertRaises(voice.CorpusError):
                voice.sanity_archive(archive)

    def test_profile_never_overwrites_original_even_with_replace(self):
        self.store.mkdir(mode=0o700)
        original = self.store / "essay.md"
        original.write_text(PROSE, encoding="utf-8")
        voice.execute(self.args("import", str(original), "--format", "text", "--attest-human"))
        with self.assertRaises(voice.CorpusError):
            self.profile("--output", str(original), "--replace")
        self.assertEqual(original.read_text(), PROSE)

    def test_profile_never_overwrites_selected_export(self):
        self.store.mkdir(mode=0o700)
        export = self.store / "source.json"
        content = json.dumps([self.envelope()])
        export.write_text(content, encoding="utf-8")
        voice.execute(self.args("import", str(export), "--format", "records", "--namespace", "personal", "--attest-human"))
        with self.assertRaises(voice.CorpusError):
            self.profile("--output", str(export), "--replace")
        self.assertEqual(export.read_text(), content)

    def test_malformed_portable_text_marks_fail_with_corpus_error(self):
        body = self.sanity()["body"]
        body[0]["children"][0]["marks"] = None
        with self.assertRaises(voice.CorpusError):
            voice.portable_text(body)

    def test_message_level_generated_authorship_is_excluded(self):
        record = self.envelope(
            messages=[
                {"role": "user", "author_id": "alex", "content": PROSE, "authorship": "ai_generated"},
                {"role": "user", "author_id": "alex", "content": OTHER, "authorship": "user_attested_original"},
            ]
        )
        file = self.export("messages.json", record)
        result = voice.execute(self.args("import", str(file), "--format", "messages", "--namespace", "personal", "--attest-human"))
        self.assertEqual(result["accepted_records"], 1)
        rows, _ = voice.select_samples(self.store, "alex")
        self.assertNotIn(PROSE, rows[0]["prose"])
        self.assertIn(OTHER, rows[0]["prose"])

    def test_generated_profile_cannot_be_reimported_as_authored_prose(self):
        self.import_text()
        output = self.store / "reference.md"
        self.profile("--output", str(output))
        result = voice.execute(self.args("import", str(output), "--format", "text", "--attest-human"))
        self.assertEqual(result["accepted_records"], 0)

    def test_case_normalized_language_selects_admitted_samples(self):
        self.import_text()
        result = voice.execute(self.args("profile", "--language", "EN"))
        self.assertEqual(result["language"], "en")

    def test_boolean_schema_version_is_invalid(self):
        with self.assertRaises(voice.CorpusError):
            self.import_records([self.envelope(schema_version=True)])

    def test_empty_comparison_is_rejected(self):
        self.import_text()
        file = self.write("empty-draft.md", "```text\nignore code\n```")
        with self.assertRaises(voice.CorpusError):
            voice.execute(self.args("compare", str(file), "--language", "en"))

    def test_profile_cannot_replace_another_authors_source(self):
        self.import_text()
        source = self.store / "sam.md"
        source.write_text(OTHER, encoding="utf-8")
        args = voice.parser().parse_args(["import", str(source), "--format", "text", "--attest-human", "--store", str(self.store), "--author", "sam"])
        voice.execute(args)
        with self.assertRaises(voice.CorpusError):
            self.profile("--output", str(source), "--replace")
        self.assertEqual(source.read_text(), OTHER)

    def test_replace_refuses_unrelated_private_files(self):
        self.import_text()
        source = self.store / "unimported.md"
        source.write_text(OTHER, encoding="utf-8")
        with self.assertRaises(voice.CorpusError):
            self.profile("--output", str(source), "--replace")
        self.assertEqual(source.read_text(), OTHER)

    def test_profile_cannot_replace_another_authors_generated_reference(self):
        self.import_text()
        source = self.write("sam.md", OTHER)
        voice.execute(voice.parser().parse_args(["import", str(source), "--format", "text", "--attest-human", "--store", str(self.store), "--author", "sam"]))
        for suffix in ("md", "json"):
            with self.subTest(suffix=suffix):
                output = self.store / ("sam-reference." + suffix)
                voice.execute(voice.parser().parse_args(["profile", "--language", "en", "--output", str(output), "--store", str(self.store), "--author", "sam"]))
                before = output.read_bytes()
                with self.assertRaises(voice.CorpusError):
                    self.profile("--output", str(output), "--replace")
                self.assertEqual(output.read_bytes(), before)

    def test_dated_source_is_not_replaced_by_unknown_revision(self):
        self.import_records([self.envelope()])
        result = self.import_records([self.envelope(text=OTHER, updated_at="")])
        self.assertEqual(result["storage_changes"], {"unknown_revision": 1})
        self.assertEqual(voice.select_samples(self.store, "alex")[0][0]["raw"], PROSE)

    def test_fractional_revision_times_are_ordered_chronologically(self):
        self.import_records([self.envelope(updated_at="2026-10-01T12:00:00.500Z")])
        result = self.import_records([self.envelope(text=OTHER, updated_at="2026-10-01T12:00:00Z")])
        self.assertEqual(result["storage_changes"], {"stale_revision": 1})
        self.assertEqual(voice.select_samples(self.store, "alex")[0][0]["raw"], PROSE)

    def test_equal_timestamp_conflicting_content_fails_closed(self):
        self.import_records([self.envelope()])
        with self.assertRaises(voice.CorpusError):
            self.import_records([self.envelope(text=OTHER)])
        self.assertEqual(voice.select_samples(self.store, "alex")[0][0]["raw"], PROSE)

    def test_private_read_checks_directory_permissions_too(self):
        if os.name != "posix":
            self.skipTest("POSIX permissions")
        self.import_text()
        self.store.chmod(0o755)
        with self.assertRaises(voice.CorpusError):
            self.profile()

    def test_profile_output_respects_deleted_source_file(self):
        self.import_text()
        source = self.store / "never-imported.json"
        source.write_text(json.dumps({"notes": OTHER}), encoding="utf-8")
        with self.assertRaises(voice.CorpusError):
            self.profile("--output", str(source), "--replace")
        self.assertIn(OTHER, source.read_text())

    def test_message_wrapper_status_and_truncation_are_checked(self):
        message = {"role": "user", "author_id": "alex", "content": PROSE}
        for fields in ({"status": "draft"}, {"status": "unknown"}, {"truncated": True}, {"truncated": None}):
            with self.subTest(fields=fields):
                record = self.envelope(messages=[message], **fields)
                file = self.export("messages.json", record)
                result = voice.execute(self.args("import", str(file), "--format", "messages", "--namespace", "personal", "--attest-human"))
                self.assertEqual(result["accepted_records"], 0)
        self.assertFalse(self.store.exists())

    def test_individual_messages_exclude_drafts_and_truncated_passages(self):
        for fields in ({"status": "draft"}, {"status": "unknown"}, {"truncated": True}, {"truncated": None}):
            with self.subTest(fields=fields):
                record = self.envelope(messages=[{"role": "user", "author_id": "alex", "content": PROSE, **fields}])
                file = self.export("messages.json", record)
                result = voice.execute(self.args("import", str(file), "--format", "messages", "--namespace", "personal", "--attest-human"))
                self.assertEqual(result["accepted_records"], 0)

    def test_explicit_draft_message_import_stays_labelled_draft(self):
        record = self.envelope(status="draft", messages=[{"role": "user", "author_id": "alex", "content": PROSE, "status": "draft"}])
        file = self.export("messages.json", record)
        result = voice.execute(self.args("import", str(file), "--format", "messages", "--namespace", "personal", "--attest-human", "--include-drafts"))
        self.assertEqual(result["accepted_records"], 1)
        self.assertEqual(voice.select_samples(self.store, "alex")[0][0]["status"], "draft")

    def test_sanity_generated_metadata_overrides_blanket_attestation(self):
        for fields in ({"authorship": "ai_generated"}, {"content_kind": "summary"}, {"authorship": None}):
            with self.subTest(fields=fields):
                result = self.import_sanity([self.sanity(**fields)])
                self.assertEqual(result["accepted_records"], 0)
        self.assertFalse(self.store.exists())

    def test_mismatched_html_closures_cannot_end_quote_suppression(self):
        malformed = "<q>quote</blockquote> " + SECRET + "</q><p>" + PROSE + "</p>"
        cleaned = voice.clean_prose(malformed)
        self.assertNotIn(SECRET, cleaned)
        self.assertIn(PROSE, cleaned)

    def test_nested_html_quotes_and_self_closing_nodes_are_safe(self):
        nested = "<blockquote><q>" + SECRET + "</q>" + SECRET + "</blockquote><code/><p>" + PROSE + "</p>"
        cleaned = voice.clean_prose(nested)
        self.assertNotIn(SECRET, cleaned)
        self.assertIn(PROSE, cleaned)

    def test_nul_and_escaped_surrogate_text_fail_without_storage(self):
        for text in (PROSE + "\x00", PROSE + "\ud800"):
            with self.subTest(text_kind=repr(text[-1])):
                file = self.export("unsafe.json", self.envelope(text=text))
                with self.assertRaises(voice.CorpusError):
                    voice.execute(self.args("import", str(file), "--format", "records", "--namespace", "personal", "--attest-human"))
        self.assertFalse(self.store.exists())

    def test_invalid_role_type_does_not_escape_cli_error_handling(self):
        file = self.export("role.json", self.envelope(speaker_role=["user"]))
        result = subprocess.run([sys.executable, str(self.script), "import", str(file), "--format", "records", "--namespace", "personal", "--author", "alex", "--attest-human", "--store", str(self.store)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.store.exists())

    def test_archive_pax_metadata_is_bounded_before_tar_parsing(self):
        archive = self.root / "metadata.tar.gz"
        with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as output:
            member = tarfile.TarInfo("data.ndjson")
            content = json.dumps(self.sanity()).encode()
            member.size = len(content)
            member.pax_headers = {"comment": "x" * 20000}
            output.addfile(member, io.BytesIO(content))
        from unittest.mock import patch
        with patch.object(voice, "MAX_ARCHIVE_BYTES", 12000):
            with self.assertRaises(voice.CorpusError):
                voice.sanity_archive(archive)

    def test_cabinet_agent_folders_are_not_scanned(self):
        self.write("cabinet/writing/story.md", PROSE)
        self.write("cabinet/.agents/editor/persona.md", SECRET)
        self.write("cabinet/.jobs/job.md", SECRET)
        self.write("cabinet/.history/old.md", SECRET)
        result = voice.execute(self.args("import", str(self.root / "cabinet"), "--format", "text", "--recursive", "--attest-human", "--dry-run"))
        self.assertEqual(result["accepted_records"], 1)

    def test_clean_checkout_has_no_personal_inputs_and_runs_from_elsewhere(self):
        checkout = self.root / "clean-checkout"
        (checkout / "scripts").mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(checkout)], check=True)
        (checkout / ".gitignore").write_text(".voice/\n", encoding="utf-8")
        (checkout / "scripts" / "voice_corpus.py").write_bytes(self.script.read_bytes())
        source = self.write("approved-writing.md", PROSE)
        private = checkout / ".voice"
        command = [sys.executable, str(checkout / "scripts" / "voice_corpus.py")]
        common = ["--store", str(private), "--author", "alex"]
        calls = [
            ["import", str(source), "--format", "text", "--attest-human"],
            ["profile", "--language", "en", "--output", str(private / "reference.md"), "--include-excerpts"],
            ["compare", str(source), "--language", "en"],
            ["delete", "--confirm"],
        ]
        for arguments in calls:
            result = subprocess.run(command + arguments + common, capture_output=True, text=True, timeout=10, cwd=self.root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)
            self.assertNotIn(PROSE, result.stdout + result.stderr)
        status = subprocess.run(
            ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, check=True
        ).stdout
        self.assertNotIn("corpus.sqlite3", status)
        self.assertNotIn("reference.md", status)
        self.assertFalse((checkout / "foundation.md").exists())
        self.assertFalse((checkout / "provenance.md").exists())

    def test_malformed_sanity_authorship_metadata_is_not_admitted(self):
        for value in (["user_attested_original"], {"source": "human"}, 1, True):
            with self.subTest(value=value):
                result = self.import_sanity([self.sanity(authorship=value)])
                self.assertEqual(result["accepted_records"], 0)
        self.assertFalse(self.store.exists())


if __name__ == "__main__":
    unittest.main()

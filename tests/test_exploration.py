"""Public-diagram boundaries tested without personal data or installed skills."""

import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import render_exploration as diagrams

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("codegraph.html", "workflow.html", "workflow-preview.svg")


class ExplorationTests(unittest.TestCase):
    def test_forbidden_tracked_path_blocks_content_read(self):
        for name in ("foundation.md", "notes/provenance.md", ".voice/profile.md", "voice-corpus/source.json", "Foundation.md"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                listing = b"100644 blob " + b"a" * 40 + b"\t" + name.encode() + b"\0"
                with patch.object(diagrams.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=listing)) as command:
                    with self.assertRaises(ValueError):
                        diagrams.public_snapshot(Path(temporary), Path(temporary) / "snapshot")
                    self.assertEqual(command.call_count, 1)
                    self.assertIn("ls-tree", command.call_args.args[0])
                    self.assertFalse((Path(temporary) / "snapshot").exists())

    def test_tracked_symlinks_block_content_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            listing = b"120000 blob " + b"a" * 40 + b"\tlinked.md\0"
            with patch.object(diagrams.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=listing)) as command:
                with self.assertRaises(ValueError):
                    diagrams.public_snapshot(Path(temporary), Path(temporary) / "snapshot")
                self.assertEqual(command.call_count, 1)

    def test_snapshot_contains_only_approved_committed_public_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
            (repo / "public.md").write_text("Synthetic public source.", encoding="utf-8")
            (repo / "foundation.md").write_text("Synthetic untracked private source.", encoding="utf-8")
            (repo / "assets/explore").mkdir(parents=True)
            (repo / "assets/explore/codegraph.html").write_text("Generated output must not be scanned.")
            subprocess.run(["git", "-C", str(repo), "add", "public.md", "assets/explore/codegraph.html"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Synthetic Test", "-c", "user.email=test@example.com", "commit", "--quiet", "-m", "Synthetic fixture"], check=True)
            snapshot = root / "snapshot"
            diagrams.public_snapshot(repo, snapshot)
            self.assertEqual((snapshot / "public.md").read_text(), "Synthetic public source.")
            self.assertFalse((snapshot / "foundation.md").exists())
            self.assertFalse((snapshot / "assets/explore").exists())

    def test_metadata_redaction_never_changes_structure(self):
        graph = {"project": {"root": "/private/build/location", "name": "temporary"},
                 "nodes": [{"id": "file:public.py"}], "edges": []}
        structure = copy.deepcopy((graph["nodes"], graph["edges"]))
        result = diagrams.public_metadata(graph, "abc123")
        self.assertNotIn("root", result["project"])
        self.assertEqual((result["nodes"], result["edges"]), structure)
        self.assertEqual(result["project"]["name"], "cv-witness")
        self.assertEqual(result["project"]["gitCommitHash"], "abc123")

    def test_incomplete_generation_preserves_published_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            staged, output = root / "staged", root / "output"
            staged.mkdir()
            output.mkdir()
            for name in NAMES:
                (output / name).write_text("previous " + name)
            (staged / "codegraph.html").write_text("new map")
            with self.assertRaises(ValueError):
                diagrams.publish_artifacts(staged, output)
            for name in NAMES:
                self.assertEqual((output / name).read_text(), "previous " + name)

    def test_publication_io_failure_rolls_back_prior_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            staged, output = root / "staged", root / "output"
            staged.mkdir()
            output.mkdir()
            for name in NAMES:
                (staged / name).write_text("new " + name)
                (output / name).write_text("previous " + name)
            original_replace = os.replace
            calls = 0

            def fail_second(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("Synthetic write failure")
                return original_replace(source, destination)

            with patch.object(diagrams.os, "replace", side_effect=fail_second):
                with self.assertRaises(OSError):
                    diagrams.publish_artifacts(staged, output)
            for name in NAMES:
                self.assertEqual((output / name).read_text(), "previous " + name)
            self.assertEqual(list(output.glob(".explore-publish-*")), [])

    def test_complete_set_is_published_without_changing_other_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            staged, output = root / "staged", root / "output"
            staged.mkdir()
            output.mkdir()
            (output / "index.html").write_text("Keep project guide.")
            for name in NAMES:
                (staged / name).write_text("new " + name)
            diagrams.publish_artifacts(staged, output)
            for name in NAMES:
                self.assertEqual((output / name).read_text(), "new " + name)
            self.assertEqual((output / "index.html").read_text(), "Keep project guide.")

    def test_published_map_has_no_local_root_or_heuristic_calls(self):
        source = (ROOT / "assets/explore/codegraph.html").read_text()
        graph = json.loads(re.search(r'<script[^>]*id="data"[^>]*>(.*?)</script>', source, flags=re.DOTALL)[1])
        self.assertNotIn("root", graph["project"])
        self.assertEqual(graph["project"]["name"], "cv-witness")
        self.assertNotIn("/Users/", source)
        self.assertNotIn("/Volumes/", source)
        self.assertTrue(graph["nodes"])
        self.assertTrue(graph["edges"])
        self.assertEqual(len(graph["tour"]), 3)
        self.assertFalse(any(edge["type"] == "calls" for edge in graph["edges"]))

    def test_workflow_is_self_contained_with_reduced_motion_and_pause(self):
        source = (ROOT / "assets/explore/workflow.html").read_text()
        self.assertIn("prefers-reduced-motion", source)
        self.assertIn('id="pauseBtn"', source)
        self.assertIn('id="themeBtn"', source)
        self.assertNotIn('<script src=', source)
        self.assertNotIn('href="https://', source)


if __name__ == "__main__":
    unittest.main()

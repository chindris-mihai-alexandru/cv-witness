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

    def test_exploration_pages_declare_valid_favicons(self):
        for name in ("index.html", "workflow.html", "codegraph.html"):
            with self.subTest(page=name):
                source = (ROOT / "assets/explore" / name).read_text(encoding="utf-8")
                icon = re.search(r'<link\b[^>]*rel="icon"[^>]*href="([^"]+)"', source)
                self.assertIsNotNone(icon, "Exploration pages must not request a missing root favicon.")
                if name == "index.html":
                    self.assertTrue((ROOT / "assets/explore" / icon[1]).is_file())
                else:
                    from urllib.parse import unquote
                    self.assertTrue(icon[1].startswith("data:image/svg+xml,"))
                    self.assertEqual(unquote(icon[1].split(",", 1)[1]),
                                     (ROOT / "assets/mark.svg").read_text(encoding="utf-8"))


    def test_exploration_prose_aligns_both_edges_without_stretching_last_lines(self):
        source = (ROOT / "assets/explore/index.html").read_text(encoding="utf-8")
        rule = re.search(r"p,\s*ol li\s*\{([^}]+)\}", source)
        self.assertIsNotNone(rule)
        declarations = dict(part.strip().split(":", 1) for part in rule[1].split(";") if part.strip())
        self.assertEqual(declarations["text-align"].strip(), "justify")
        self.assertEqual(declarations["text-align-last"].strip(), "left")
        self.assertEqual(declarations["hyphens"].strip(), "auto")
        intro = re.search(r"\.intro\s*\{([^}]+)\}", source)
        self.assertNotIn("max-width", intro[1])
        self.assertIn('<html lang="en">', source)
        code = re.search(r"code\s*\{([^}]+)\}", source)
        self.assertIn("hyphens:none", code[1])

    def test_readme_preview_is_fixed_light_static_and_preserves_geometry(self):
        import xml.etree.ElementTree as ET
        source = (ROOT / "assets/explore/workflow.html").read_text(encoding="utf-8")
        original = ET.fromstring(re.search(r'(<svg id="flowsvg".*?</svg>)', source, re.DOTALL)[1])
        preview_source = diagrams.workflow_preview(source)
        preview = ET.fromstring(preview_source)
        tag = lambda element: element.tag.rsplit("}", 1)[-1]
        background = next(element for element in preview.iter()
                          if element.get("id") == "preview-background")
        self.assertEqual(background.get("fill"), "#f8fafc")
        self.assertEqual(preview.get("viewBox"), original.get("viewBox"))
        self.assertEqual(preview.get("width"), "600")
        self.assertGreater(int(preview.get("height")), 600)
        self.assertNotIn("var(", preview_source)
        self.assertNotIn("context-stroke", preview_source)
        self.assertFalse(any(tag(element) in {"style", "script", "animate", "animateMotion", "filter"}
                             for element in preview.iter()))
        original_labels = ["".join(element.itertext()) for element in original.iter()
                           if tag(element) == "text"]
        preview_labels = ["".join(element.itertext()) for element in preview.iter()
                          if tag(element) == "text"]
        self.assertEqual(preview_labels, original_labels)
        original_paths = [element.get("d") for element in original.iter()
                          if element.get("class") in {"flow", "flow-async"}]
        preview_paths = [element.get("d") for element in preview.iter()
                         if element.get("class") in {"flow", "flow-async"}]
        self.assertEqual(preview_paths, original_paths)
        self.assertTrue(all(element.get("fill") in {"#0f172a", "#475569"}
                            for element in preview.iter() if tag(element) == "text"))

    def test_published_readme_preview_has_an_opaque_light_background(self):
        import xml.etree.ElementTree as ET
        source = (ROOT / "assets/explore/workflow-preview.svg").read_text(encoding="utf-8")
        preview = ET.fromstring(source)
        background = next((element for element in preview.iter()
                           if element.get("id") == "preview-background"), None)
        self.assertIsNotNone(background)
        self.assertEqual(background.get("fill"), "#f8fafc")
        self.assertNotIn("var(", source)
        self.assertTrue(all(not value or value.startswith("#")
                            for element in preview.iter()
                            for key, value in element.attrib.items()
                            if key.rsplit("}", 1)[-1] == "href"))

    def test_preview_only_needs_no_plugins_and_leaves_other_artifacts_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "assets/explore"
            output.mkdir(parents=True)
            workflow = (ROOT / "assets/explore/workflow.html").read_bytes()
            (output / "workflow.html").write_bytes(workflow)
            (output / "codegraph.html").write_text("Keep the public source map.")
            (output / "workflow-preview.svg").write_text("Previous preview.")
            with patch.object(diagrams, "ROOT", root), patch.object(diagrams.subprocess, "run") as command:
                diagrams.main(["--preview-only"])
                command.assert_not_called()
            self.assertIn('fill="#f8fafc"', (output / "workflow-preview.svg").read_text())
            self.assertEqual((output / "workflow.html").read_bytes(), workflow)
            self.assertEqual((output / "codegraph.html").read_text(), "Keep the public source map.")
            self.assertEqual(list(output.glob(".workflow-preview-*")), [])

    def test_failed_preview_conversion_preserves_previous_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "assets/explore"
            output.mkdir(parents=True)
            (output / "workflow.html").write_text("Malformed synthetic workflow.")
            preview = output / "workflow-preview.svg"
            preview.write_text("Keep previous image.")
            with patch.object(diagrams, "ROOT", root), patch.object(diagrams, "workflow_preview", side_effect=ValueError("Synthetic conversion failure")):
                with self.assertRaises(ValueError):
                    diagrams.main(["--preview-only"])
            self.assertEqual(preview.read_text(), "Keep previous image.")
            self.assertEqual(list(output.glob(".workflow-preview-*")), [])

    def test_preview_only_rejects_symlinked_directories_before_reading_source(self):
        for linked_part in ("assets", "explore"):
            with self.subTest(linked_part=linked_part), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                outside = root / "outside"
                outside.mkdir()
                (outside / "workflow.html").write_text("Synthetic source must not be read.")
                previous = outside / "workflow-preview.svg"
                previous.write_text("Preserve outside preview.")
                if linked_part == "assets":
                    clone = root / "clone"
                    clone.mkdir()
                    (clone / "assets").symlink_to(outside, target_is_directory=True)
                else:
                    clone = root / "clone"
                    (clone / "assets").mkdir(parents=True)
                    (clone / "assets/explore").symlink_to(outside, target_is_directory=True)
                with patch.object(diagrams, "ROOT", clone), \
                        patch.object(Path, "read_text", side_effect=AssertionError("Source read preceded path validation")), \
                        patch.object(diagrams, "workflow_preview") as convert:
                    with self.assertRaises(ValueError):
                        diagrams.main(["--preview-only"])
                    convert.assert_not_called()
                self.assertEqual(previous.read_text(), "Preserve outside preview.")
                self.assertEqual(list(outside.glob(".workflow-preview-*")), [])


if __name__ == "__main__":
    unittest.main()

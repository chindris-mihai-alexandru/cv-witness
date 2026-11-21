"""Regression tests for preflight robustness and HF stack recognition.

Fictional data only; no real names, tokens or private foundation content.
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import preflight
import bullet_audit


class PreflightTimeoutTest(unittest.TestCase):
    def test_yc_timeout_degrades_to_empty_not_crash(self):
        real_run = subprocess.run
        real_which = preflight.shutil.which

        def timeout_run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd=a[0] if a else "yc", timeout=1)

        try:
            preflight.shutil.which = lambda name: "/usr/bin/yc" if name == "yc" else None
            subprocess.run = timeout_run
            self.assertEqual(preflight.fetch_yc_postings("engineer", 5), [])
        finally:
            subprocess.run = real_run
            preflight.shutil.which = real_which


class BulletAuditToolRecognitionTest(unittest.TestCase):
    def test_hf_stack_tools_are_recognized(self):
        text = "Built a Gradio demo with LightGBM and ChromaDB on Hugging Face."
        found = set(bullet_audit.TOOL_RE.findall(text))
        # The regex uses a non-capturing group, so findall returns whole matches.
        self.assertTrue(any("Gradio" in m for m in found))
        self.assertTrue(any("LightGBM" in m for m in found))
        self.assertTrue(any("ChromaDB" in m for m in found))
        self.assertTrue(any("Hugging" in m for m in found))

    def test_existing_stack_still_recognized(self):
        text = "Automated pipelines with PowerShell and Azure DevOps."
        found = bullet_audit.TOOL_RE.findall(text)
        self.assertTrue(any("PowerShell" in m for m in found))
        self.assertTrue(any("Azure" in m for m in found))


if __name__ == "__main__":
    unittest.main()
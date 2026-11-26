"""Tests for owner-only artifact writes outside a public checkout."""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import private_files as private  # noqa: E402


class PrivateOutputTest(unittest.TestCase):
    def test_external_write_is_atomic_and_owner_only(self):
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "private" / "snapshot.json"
            result = private.write_private_text(destination, "{}")
            self.assertEqual(result, destination)
            self.assertEqual(stat.S_IMODE(os.stat(destination).st_mode), 0o600)
            self.assertEqual(destination.read_text(encoding="utf-8"), "{}")
            self.assertFalse(list(destination.parent.glob(".private-*")))

    def test_public_checkout_write_is_rejected(self):
        with self.assertRaises(private.PrivateOutputError):
            private.private_destination(SCRIPTS.parent / "assets" / "private-snapshot.json")

    def test_symlinked_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "real"
            directory.mkdir()
            link = Path(root) / "link"
            link.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(private.PrivateOutputError):
                private.private_destination(link / "snapshot.json")


if __name__ == "__main__":
    unittest.main()

"""Privacy guard: public test/example fixtures must not carry real personal data.

cv-witness is a general skill for any user. Its committed fixtures use fictional
people and reserved example domains. This guard fails if a real-looking email
address (any domain other than the reserved example.* domains) leaks into a
committed test or example file. It stores no personal identifiers itself.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
RESERVED = {"example.com", "example.org", "example.net", "example.edu"}
SCAN_DIRS = ("tests", "examples")
SCAN_SUFFIXES = {".py", ".json", ".md", ".txt"}


def _is_reserved(domain):
    domain = domain.lower()
    return domain in RESERVED or domain.endswith(".example")


class FixturePrivacyTests(unittest.TestCase):
    def test_fixture_emails_use_reserved_domains(self):
        violations = []
        for dirname in SCAN_DIRS:
            for path in sorted((ROOT / dirname).rglob("*")):
                if path.suffix not in SCAN_SUFFIXES or not path.is_file():
                    continue
                for match in EMAIL.finditer(path.read_text(encoding="utf-8", errors="replace")):
                    if not _is_reserved(match.group(1)):
                        violations.append(f"{path.relative_to(ROOT)}: {match.group(0)}")
        self.assertEqual(violations, [], "Real-looking email(s) in public fixtures; use reserved example.* domains.")


if __name__ == "__main__":
    unittest.main()

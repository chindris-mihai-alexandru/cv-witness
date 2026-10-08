#!/usr/bin/env python3
"""Render the public synthetic example with the canonical template and renderer.

Run from any directory: python3 scripts/render_sample.py
Requires the same macOS browser as render.sh, plus Poppler's PDF tools.
Only examples/sample-cv.json is read; private resume sources are never used.
"""

import html
import json
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def main():
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    fields = json.loads((ROOT / "examples/sample-cv.json").read_text(encoding="utf-8"))["fields"]
    required = set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", template))
    if set(fields) != required:
        raise ValueError(f"Sample fields differ from template: missing={required - set(fields)}, extra={set(fields) - required}")
    filled = re.sub(r"\{\{([A-Z0-9_]+)\}\}", lambda match: html.escape(fields[match[1]], quote=True), template)
    with tempfile.TemporaryDirectory(prefix="cv-witness-sample-") as temporary:
        directory = Path(temporary)
        source = directory / "sample.html"
        pdf = directory / "sample.pdf"
        source.write_text(filled, encoding="utf-8")
        print(run("/bin/zsh", str(ROOT / "render.sh"), str(source), str(pdf)).strip())
        info = run("pdfinfo", str(pdf))
        if not re.search(r"^Pages:\s+1\s*$", info, flags=re.MULTILINE):
            raise ValueError("The public sample must fit on one page.")
        text = run("pdftotext", str(pdf), "-")
        expected = ("Alex Morgan", "Professional Summary", "Skills", "Certifications", "Professional Experience", "Projects", "Education", "Languages", "Example Studio (fictional)")
        if any(value.casefold() not in text.casefold() for value in expected):
            raise ValueError("A sample section or fictional-source label did not extract.")
        if "{{" in text or "[FILL" in text or "\ufffd" in text:
            raise ValueError("The sample contains an unresolved marker or replacement glyph.")
        run("pdftoppm", "-f", "1", "-l", "1", "-scale-to", "2000", "-singlefile", "-png", str(pdf), str(directory / "sample"))
        image = directory / "sample.png"
        width, height = struct.unpack(">II", image.read_bytes()[16:24])
        assets = ROOT / "assets"
        shutil.copyfile(pdf, assets / "sample-cv.pdf")
        shutil.copyfile(image, assets / "sample-cv.png")
        print(f"Verified synthetic sample: 1 page, {len(required)} fields, {width}x{height} PNG.")
        print("Published outputs: assets/sample-cv.pdf and assets/sample-cv.png")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Sample render failed: {error}") from error

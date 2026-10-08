#!/usr/bin/env python3
"""Render the public synthetic example with the canonical template and renderer.

Run from any directory: python3 scripts/render_sample.py
Requires a Chromium-family browser and Poppler's PDF tools.
Only examples/sample-cv.json is read; private resume sources are never used.
"""

import argparse
import html
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

if __package__:
    from .render_cv import render_html
else:
    from render_cv import render_html

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets", help="Only synthetic PDF/PNG outputs are written here")
    args = parser.parse_args(argv)
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    fields = json.loads((ROOT / "examples/sample-cv.json").read_text(encoding="utf-8"))["fields"]
    required = set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", template))
    if set(fields) != required:
        raise ValueError(f"Sample fields differ from template: missing={required - set(fields)}, extra={set(fields) - required}")
    filled = re.sub(r"\{\{([A-Z0-9_]+)\}\}", lambda match: html.escape(fields[match[1]], quote=True), template)
    with tempfile.TemporaryDirectory(prefix="cv-witness-sample-") as temporary:
        directory = Path(temporary).resolve()
        pdf = directory / "sample.pdf"
        expected = ("Alex Morgan", "Professional Summary", "Skills", "Certifications", "Professional Experience", "Projects", "Education", "Languages", "Example Studio (fictional)")
        render_html(filled, pdf, expected_text=expected,
                    no_sandbox=os.environ.get("CV_WITNESS_CI_NO_SANDBOX") == "1")
        run("pdftoppm", "-f", "1", "-l", "1", "-scale-to", "2000", "-singlefile", "-png", str(pdf), str(directory / "sample"))
        image = directory / "sample.png"
        width, height = struct.unpack(">II", image.read_bytes()[16:24])
        assets = args.output_dir.expanduser().resolve()
        assets.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, assets / "sample-cv.pdf")
        shutil.copyfile(image, assets / "sample-cv.png")
        print(f"Verified synthetic sample: 1 page, {len(required)} fields, {width}x{height} PNG.")
        print("Published synthetic sample PDF and PNG.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Sample render failed: {error}") from error

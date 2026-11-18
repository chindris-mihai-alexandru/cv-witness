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


BLOCK_FIELDS = {"SUMMARY_2", "SKILLS_BLOCK", "CERTS_BLOCK", "ROLES_BLOCK", "PROJECTS_BLOCK", "EDUCATION_BLOCK"}
SECTION_HEADINGS = ("Professional Summary", "Skills", "Certifications", "Professional Experience", "Projects", "Education", "Languages")


def fill_template(template, fields):
    """Fill the canonical house-style template. Scalar fields are HTML-escaped;
    block fields are trusted HTML supplied by the caller. The field set must
    match the template's placeholders exactly (no missing, no extra)."""
    required = set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", template))
    if set(fields) != required:
        raise ValueError(f"Fields differ from template: missing={required - set(fields)}, extra={set(fields) - required}")

    def fill(match):
        name = match[1]
        value = fields[name]
        return value if name in BLOCK_FIELDS else html.escape(value, quote=True)

    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", fill, template)


def render_fields(fields, pdf, expected_text=(), no_sandbox=False, max_pages=1):
    """Render any fields dict through the canonical template + checked renderer.
    This is the single house-style path: the public synthetic sample and any
    tailored CV use the same template and renderer, so their format matches."""
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    filled = fill_template(template, fields)
    return render_html(filled, pdf, max_pages=max_pages, expected_text=expected_text,
                       no_sandbox=no_sandbox, replace=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets", help="Only synthetic PDF/PNG outputs are written here")
    parser.add_argument("--fields", type=Path, help="Render an arbitrary fields JSON (with a 'fields' key or a bare dict) through the canonical template instead of the synthetic sample")
    parser.add_argument("--output", type=Path, help="PDF destination when --fields is given")
    args = parser.parse_args(argv)
    no_sandbox = os.environ.get("CV_WITNESS_CI_NO_SANDBOX") == "1"
    if args.fields:
        if not args.output:
            raise ValueError("--fields requires --output")
        payload = json.loads(args.fields.expanduser().read_text(encoding="utf-8"))
        fields = payload["fields"] if isinstance(payload, dict) and "fields" in payload else payload
        expected = (fields.get("NAME", ""),) + SECTION_HEADINGS
        report = render_fields(fields, args.output.expanduser().resolve(), expected_text=expected, no_sandbox=no_sandbox)
        print(f"Rendered {args.output}: {report.get('pages')} page(s), {report.get('text_words')} words, passed={report.get('passed')}.")
        return
    fields = json.loads((ROOT / "examples/sample-cv.json").read_text(encoding="utf-8"))["fields"]
    with tempfile.TemporaryDirectory(prefix="cv-witness-sample-") as temporary:
        directory = Path(temporary).resolve()
        pdf = directory / "sample.pdf"
        expected = ("Alex Morgan",) + SECTION_HEADINGS + ("Example Studio (fictional)",)
        render_fields(fields, pdf, expected_text=expected, no_sandbox=no_sandbox)
        run("pdftoppm", "-f", "1", "-l", "1", "-scale-to", "2000", "-singlefile", "-png", str(pdf), str(directory / "sample"))
        image = directory / "sample.png"
        width, height = struct.unpack(">II", image.read_bytes()[16:24])
        assets = args.output_dir.expanduser().resolve()
        assets.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, assets / "sample-cv.pdf")
        shutil.copyfile(image, assets / "sample-cv.png")
        print(f"Verified synthetic sample: 1 page, {len(fields)} fields, {width}x{height} PNG.")
        print("Published synthetic sample PDF and PNG.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Sample render failed: {error}") from error

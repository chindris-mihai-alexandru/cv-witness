#!/usr/bin/env python3
"""Render only the tracked fictional fixture into the public template gallery."""

import argparse
import json
import os
from pathlib import Path

if __package__:
    from .build_cv import LANES, build_html, load_document
    from .render_cv import render_html
else:
    from build_cv import LANES, build_html, load_document
    from render_cv import render_html

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets/explore/samples")
    args = parser.parse_args(argv)
    data = load_document(ROOT / "examples/structured-cv.json")
    directory = args.output_dir.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    for lane in LANES:
        source, expected, _ = build_html(data, lane)
        for paper in ("a4", "letter"):
            report = render_html(source, directory / f"{lane}-{paper}.pdf", paper,
                                 max_pages=2, expected_text=expected, replace=True,
                                 no_sandbox=os.environ.get("CV_WITNESS_CI_NO_SANDBOX") == "1")
            print(json.dumps({"lane": lane, "paper": paper, "pages": report["pages"],
                              "passed": report["passed"]}))


if __name__ == "__main__":
    main()

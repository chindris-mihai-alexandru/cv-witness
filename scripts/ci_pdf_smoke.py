#!/usr/bin/env python3
"""Bounded CI-only browser diagnostic. This generates fictional text only."""

import os
from pathlib import Path
import tempfile
import time

from cv_checks import CheckError, validate_pdf
from render_cv import browser_path, browser_command, run_browser


def main():
    if os.environ.get("CI", "").lower() != "true":
        raise SystemExit("This diagnostic is for an isolated CI runner.")
    browser = browser_path()
    print("Synthetic PDF smoke: starting selected browser", flush=True)
    with tempfile.TemporaryDirectory(prefix="cv-witness-ci-smoke-") as temporary:
        root = Path(temporary).resolve()
        source = root / "synthetic.html"
        pdf = root / "synthetic.pdf"
        source.write_text('<!doctype html><meta charset="utf-8"><style>@page{size:A4;margin:16mm}</style><h1>Synthetic export smoke</h1><p>Fictional text only.</p>', encoding="utf-8")
        command = browser_command(browser, source, pdf, root / "profile",
                                  os.environ.get("CV_WITNESS_CI_NO_SANDBOX") == "1")
        start = time.monotonic()
        diagnostics = root / "browser-stderr.txt"
        try:
            with diagnostics.open("wb") as log:
                run_browser(command, pdf, timeout=20, stderr=log)
            report = validate_pdf(pdf, expected_text=["Synthetic export smoke"])
            if not report["passed"]:
                raise CheckError("Synthetic candidate failed PDF checks.")
        except CheckError as error:
            print(f"Synthetic smoke failed after {time.monotonic()-start:.1f}s: {error}", flush=True)
            with diagnostics.open("rb") as log:
                print(log.read(8192).decode("utf-8", errors="replace"), flush=True)
            raise SystemExit(1)
        print(f"Synthetic export ready in {time.monotonic()-start:.1f}s; PDF validation passed.", flush=True)


if __name__ == "__main__":
    main()

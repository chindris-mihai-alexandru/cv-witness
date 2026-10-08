#!/usr/bin/env python3
"""Render self-contained local HTML and check the PDF before publishing it."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

if __package__:
    from .cv_checks import CheckError, CheckFailure, MARKER, MAX_BYTES, validate_pdf
else:
    from cv_checks import CheckError, CheckFailure, MARKER, MAX_BYTES, validate_pdf

MAC_BROWSERS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


def browser_path(explicit=None):
    explicit = explicit or os.environ.get("CV_WITNESS_BROWSER")
    choices = [explicit]
    choices += list(MAC_BROWSERS)
    choices += [shutil.which(name) for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge")]
    for choice in choices:
        if not choice:
            continue
        executable = Path(choice).expanduser()
        if executable.is_file() and os.access(executable, os.X_OK):
            return str(executable.absolute())
        if explicit:
            break
    raise CheckError("No Chromium-family browser found; set --browser or CV_WITNESS_BROWSER to an executable.")


def page_css(source, paper):
    """Override the one explicit paper declaration, never silently use browser defaults."""
    if paper not in {"a4", "letter"}:
        raise CheckError("Paper must be a4 or letter.")
    matches = list(re.finditer(r"@page\s*\{[^{}]*\}", source, flags=re.I))
    if len(matches) != 1:
        raise CheckError("Self-contained HTML must have exactly one explicit @page rule.")
    rule = matches[0]
    size = re.compile(r"(?<![-\w])size\s*:\s*[^;{}]+(?=;|\})", re.I)
    if len(size.findall(rule[0])) != 1:
        raise CheckError("The @page rule must declare exactly one paper size.")
    replacement = size.sub("size: " + ("A4" if paper == "a4" else "letter"), rule[0])
    return source[:rule.start()] + replacement + source[rule.end():]


def checked_source(path, paper):
    path = Path(path).expanduser().absolute()
    if path.suffix.lower() not in {".html", ".htm"} or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise CheckError("Select a nonempty, self-contained HTML file within 16 MiB.")
    try:
        source = path.read_text(encoding="utf-8-sig")
    except UnicodeError as error:
        raise CheckError("Source HTML must be UTF-8.") from error
    return validate_source(source, paper)


def validate_source(source, paper):
    if not isinstance(source, str) or not source.strip() or len(source.encode("utf-8")) > MAX_BYTES:
        raise CheckError("Source HTML must be nonempty UTF-8 text within 16 MiB.")
    if MARKER.search(source):
        raise CheckError("Source HTML contains unresolved template or fill markers.")
    # The bundled templates are self-contained. Rendering arbitrary remote HTML is out of scope.
    if re.search(r"<script\b|<(?:iframe|object|embed)\b|<base\b|@import\b|url\s*\(", source, re.I):
        raise CheckError("Source HTML must be self-contained, without scripts, embeds or CSS resource loads.")
    if re.search(r"\b(?:src|srcset)\s*=", source, re.I) or re.search(r"<link\b[^>]*rel\s*=\s*[\"']?stylesheet", source, re.I):
        raise CheckError("External or relative render assets are not supported; use inline text and styles.")
    return page_css(source, paper)


def complete_pdf(path):
    """A write-completion signal only; Poppler still validates the candidate."""
    try:
        size = path.stat().st_size
        if not 8 < size <= MAX_BYTES:
            return None
        with path.open("rb") as document:
            if document.read(5) != b"%PDF-":
                return None
            document.seek(max(0, size - 1024))
            if not document.read().rstrip().endswith(b"%%EOF"):
                return None
        return size
    except OSError:
        return None


def browser_command(browser, source, pdf, profile, no_sandbox=False):
    command = [browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
               "--disable-background-networking", "--disable-extensions",
               "--no-first-run", "--no-default-browser-check",
               "--host-resolver-rules=MAP * ~NOTFOUND",
               "--user-data-dir=" + str(profile), "--print-to-pdf=" + str(pdf)]
    if no_sandbox:
        command.append("--no-sandbox")
    return command + [source.as_uri()]


def run_browser(command, pdf, timeout=90, stderr=subprocess.DEVNULL):
    """Wait for a stable candidate, not an indefinitely lingering browser UI."""
    try:
        with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stderr,
                              start_new_session=True) as process:
            deadline = time.monotonic() + timeout
            previous_size = None
            stable_since = None
            try:
                while time.monotonic() < deadline:
                    size = complete_pdf(pdf)
                    if size is not None:
                        if size != previous_size:
                            stable_since = time.monotonic()
                        elif time.monotonic() - stable_since >= .5:
                            if process.poll() not in (None, 0):
                                raise CheckError("Browser exited unsuccessfully; no output was published.")
                            return
                    else:
                        stable_since = None
                    previous_size = size
                    if process.poll() is not None and size is None:
                        raise CheckError("Browser produced no completed PDF; no output was published.")
                    time.sleep(.1)
                raise CheckError("Browser PDF production timed out; no output was published.")
            finally:
                # A separate session and fresh profile isolate this invocation.
                # Never search for or stop the user's shared browser.
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=2)
    except (OSError, subprocess.SubprocessError) as error:
        raise CheckError("Browser rendering failed; no output was published.") from error


def render_html(source, output, paper="a4", max_pages=1, expected_text=(),
                posting=None, overlap_policy="strict", explicit_browser=None,
                replace=False, no_sandbox=False):
    output = Path(os.path.abspath(Path(output).expanduser()))
    if any(component.is_symlink() for component in (output,) + tuple(output.parents)):
        raise CheckError("Output paths must not follow symlinked files or directories; use a canonical destination.")
    if output.suffix.lower() != ".pdf":
        raise CheckError("Output must be a non-symlink PDF path.")
    if output.exists() and not replace:
        raise CheckError("Output already exists; use --replace only for an intentional replacement.")
    if output.exists() and (not output.is_file() or output.stat().st_nlink != 1):
        raise CheckError("Output must be an ordinary, non-linked file.")
    if type(max_pages) is not int or not 1 <= max_pages <= 30:
        raise CheckError("Choose an explicit page limit between 1 and 30.")
    source = validate_source(source, paper)
    if no_sandbox and os.environ.get("CI", "").lower() != "true":
        raise CheckError("Disabling the browser sandbox requires an explicitly isolated CI runner (CI=true).")
    browser = browser_path(explicit_browser)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cv-witness-render-") as temporary:
        directory = Path(temporary)
        html_path = directory / "source.html"
        pdf_path = directory / "candidate.pdf"
        html_path.write_text(source, encoding="utf-8")
        command = browser_command(browser, html_path, pdf_path, directory / "browser-profile", no_sandbox)
        run_browser(command, pdf_path)
        report = validate_pdf(pdf_path, paper, max_pages, expected_text, posting,
                              overlap_policy, source_html=source)
        if not report["passed"]:
            raise CheckFailure(report)
        descriptor, staging = tempfile.mkstemp(prefix=".cv-witness-", suffix=".pdf", dir=output.parent)
        try:
            with os.fdopen(descriptor, "wb") as destination, pdf_path.open("rb") as candidate:
                shutil.copyfileobj(candidate, destination)
                destination.flush()
                os.fsync(destination.fileno())
            if replace:
                os.replace(staging, output)
            else:
                # Publish without clobbering a file created since the initial check.
                os.link(staging, output)
        finally:
            if os.path.exists(staging):
                os.unlink(staging)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("paper", nargs="?", choices=("a4", "letter"), default="a4")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--expected-text", action="append", default=[])
    parser.add_argument("--posting", help="Selected local posting; runs overlap checks automatically")
    parser.add_argument("--overlap-policy", choices=("strict", "review"), default="strict")
    parser.add_argument("--browser")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--no-sandbox", action="store_true", help="Only for an already isolated CI/container")
    args = parser.parse_args(argv)
    try:
        source = checked_source(args.input, args.paper)
        report = render_html(source, args.output, args.paper, args.max_pages, args.expected_text,
                             args.posting, args.overlap_policy, args.browser,
                             args.replace, args.no_sandbox)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except CheckFailure as error:
        print(json.dumps(error.report, ensure_ascii=False, indent=2))
        return 1
    except (CheckError, OSError) as error:
        print("render-cv: " + (str(error) if isinstance(error, CheckError) else "Local output operation failed."), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

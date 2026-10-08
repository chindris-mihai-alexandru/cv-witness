"""Shared, local CV export checks. These are not an ATS certification."""

from collections import defaultdict
import os
from pathlib import Path
import re
import selectors
import subprocess
import time
import unicodedata

MAX_BYTES = 16 * 1024 * 1024
MAX_WORDS = 20000
MAX_PAIRS = 100000
PAPER_POINTS = {"a4": (595.28, 841.89), "letter": (612.0, 792.0)}
MARKER = re.compile(r"\{\{[^{}]*\}\}|\[(?:FILL|TODO|TBD)(?:\s*[:\]]|\b)", re.I)


class CheckError(ValueError):
    """Invalid input or unavailable local export tools; never echo passages."""


class CheckFailure(CheckError):
    def __init__(self, report):
        self.report = report
        super().__init__("CV export failed pre-delivery checks; inspect the reported check codes.")


def run_tool(arguments, timeout=60):
    """Bound extracted stdout while discarding potentially private diagnostics."""
    try:
        with subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              env={**os.environ, "LC_ALL": "C"}) as process:
            output = bytearray()
            deadline = time.monotonic() + timeout
            try:
                with selectors.DefaultSelector() as ready:
                    ready.register(process.stdout, selectors.EVENT_READ)
                    while ready.get_map():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise CheckError("Local export tool timed out.")
                        for key, _ in ready.select(min(remaining, 1)):
                            chunk = os.read(key.fileobj.fileno(), 65536)
                            if not chunk:
                                ready.unregister(key.fileobj)
                                continue
                            if len(output) + len(chunk) > MAX_BYTES:
                                raise CheckError("Export tool output exceeds the text-size limit.")
                            output.extend(chunk)
                process.wait(timeout=max(.01, deadline - time.monotonic()))
                if process.returncode:
                    raise CheckError("Local export tool failed; verify the input and installation.")
                return output.decode("utf-8", errors="strict")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    except FileNotFoundError as error:
        raise CheckError("Required local tool is missing: " + arguments[0]) from error
    except (subprocess.SubprocessError, UnicodeError, OSError) as error:
        raise CheckError("Local export tool failed; check the input, permissions and tool installation.") from error


def read_text(path, pdf_allowed=True):
    path = Path(path).expanduser().absolute()
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise CheckError("Input is missing, not a regular file, or exceeds 16 MiB.")
    if path.suffix.lower() == ".pdf" and pdf_allowed:
        # Preserve printed hyphens in wrapped URLs and technical identifiers.
        return run_tool(["pdftotext", "-layout", str(path), "-"])
    if path.suffix.lower() not in {".txt", ".md", ".html"}:
        raise CheckError("Use a PDF, UTF-8 text or Markdown input as appropriate.")
    try:
        return path.read_text(encoding="utf-8-sig", errors="strict")
    except (OSError, UnicodeError) as error:
        raise CheckError("Text input must be readable UTF-8.") from error


def words(text):
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)


def shared_runs(cv_text, posting_text, minimum=4):
    """Find maximal contiguous shared runs; preserve word offsets, not sentences."""
    cv, posting = words(cv_text), words(posting_text)
    if not cv or not posting:
        raise CheckError("CV and posting must both contain readable words.")
    if max(len(cv), len(posting)) > MAX_WORDS:
        raise CheckError("Phrase review exceeds 20,000 words; select the relevant document.")
    index = defaultdict(list)
    for position in range(len(posting) - minimum + 1):
        index[tuple(posting[position:position + minimum])].append(position)
    matches = {}
    pairs = 0
    for position in range(len(cv) - minimum + 1):
        for target in index.get(tuple(cv[position:position + minimum]), ()):
            pairs += 1
            if pairs > MAX_PAIRS:
                raise CheckError("Phrase review has too many repetitive matches; narrow the selected inputs.")
            if position and target and cv[position - 1] == posting[target - 1]:
                continue
            length = minimum
            while position + length < len(cv) and target + length < len(posting) and cv[position + length] == posting[target + length]:
                length += 1
            phrase = tuple(cv[position:position + length])
            matches.setdefault(phrase, {"words": length, "cv_word": position + 1,
                                         "posting_word": target + 1, "phrase": " ".join(phrase)})
    return sorted(matches.values(), key=lambda item: (-item["words"], item["cv_word"], item["posting_word"]))


def overlap_report(cv_text, posting_text, show_phrases=False):
    runs = shared_runs(cv_text, posting_text)
    safe_runs = [{key: value for key, value in run.items() if show_phrases or key != "phrase"} for run in runs[:50]]
    return {"cv_words": len(words(cv_text)), "posting_words": len(words(posting_text)),
            "shared_runs": len(runs), "longest_run_words": max((r["words"] for r in runs), default=0),
            "runs": safe_runs, "reported_runs": len(safe_runs),
            "note": "Literal overlap is a review signal. Generic industry wording can match; no originality or ATS score is certified."}


def normalized_text(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def validate_pdf(path, paper="a4", max_pages=1, expected_text=(), posting=None,
                 overlap_policy="strict", show_phrases=False, source_html=None):
    if paper not in PAPER_POINTS or type(max_pages) is not int or not 1 <= max_pages <= 30:
        raise CheckError("Use A4 or Letter and an explicit page limit between 1 and 30.")
    if overlap_policy not in {"strict", "review"}:
        raise CheckError("Overlap policy must be strict or review.")
    path = Path(path).expanduser().absolute()
    if path.suffix.lower() != ".pdf" or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise CheckError("Select a nonempty PDF within the 16 MiB input limit.")
    with path.open("rb") as document:
        if document.read(5) != b"%PDF-":
            raise CheckError("Input has no PDF signature.")
    info = run_tool(["pdfinfo", str(path)])
    pages_match = re.search(r"^Pages:\s*(\d+)\s*$", info, flags=re.MULTILINE)
    if not pages_match:
        raise CheckError("pdfinfo did not report a readable page count.")
    page_count = int(pages_match[1])
    if not 1 <= page_count <= 100:
        raise CheckError("PDF page count is outside the supported CV range.")
    page_info = run_tool(["pdfinfo", "-f", "1", "-l", str(page_count), "-box", str(path)])
    sizes = re.findall(r"^Page\s+\d+\s+size:\s*([\d.]+)\s+x\s+([\d.]+)\s+pts", page_info, flags=re.MULTILINE)
    if not sizes and page_count == 1:
        sizes = re.findall(r"^Page size:\s*([\d.]+)\s+x\s+([\d.]+)\s+pts", page_info, flags=re.MULTILINE)
    text = read_text(path)
    problems = []
    if page_count > max_pages:
        problems.append({"code": "page_limit", "actual": page_count, "maximum": max_pages})
    expected_size = PAPER_POINTS[paper]
    if len(sizes) != page_count or any(abs(float(value) - expected_size[i]) > 1.5 for size in sizes for i, value in enumerate(size)):
        problems.append({"code": "paper_geometry", "expected": paper})
    if re.search(r"^Encrypted:\s*yes", info, flags=re.MULTILINE):
        problems.append({"code": "encrypted_pdf"})
    extracted_pages = text.split("\f")
    if extracted_pages and not extracted_pages[-1].strip():
        extracted_pages.pop()
    if len(extracted_pages) != page_count or any(not words(page) for page in extracted_pages):
        problems.append({"code": "empty_or_image_only_page"})
    if MARKER.search(text):
        problems.append({"code": "unresolved_marker"})
    if "\ufffd" in text or "\x00" in text:
        problems.append({"code": "invalid_extracted_glyph"})
    if source_html is not None and MARKER.search(source_html):
        problems.append({"code": "unresolved_source_marker"})
    normalized = normalized_text(text)
    for number, expected in enumerate(expected_text, 1):
        if not isinstance(expected, str) or not expected.strip():
            raise CheckError("Expected-text contract must contain nonempty strings.")
        needle = normalized_text(expected)
        # Printed links can wrap within a token; collapse extraction whitespace
        # only for explicit URL expectations, never for arbitrary prose.
        is_url = bool(re.match(r"^(?:https?://|mailto:|tel:)", needle))
        present = needle in normalized
        if is_url:
            present = re.sub(r"\s+", "", needle) in re.sub(r"\s+", "", normalized)
        if not present:
            problems.append({"code": "missing_expected_text", "item": number})
    overlap = None
    if posting is not None:
        overlap = overlap_report(text, read_text(posting, pdf_allowed=False), show_phrases)
        if overlap_policy == "strict" and overlap["shared_runs"]:
            problems.append({"code": "posting_phrase_overlap", "runs": overlap["shared_runs"]})
    report = {"passed": not problems, "paper": paper, "pages": page_count,
              "max_pages": max_pages, "text_words": len(words(text)),
              "expected_text_items": len(expected_text), "problems": problems,
              "posting_review": overlap,
              "review_required": ["Verify every CV fact with the selected sources.",
                                  "Inspect the rendered pages for clipping, reading order and legibility.",
                                  "These checks do not certify ATS parsing, ranking or an interview."]}
    return report

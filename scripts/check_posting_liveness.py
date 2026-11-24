"""Posting liveness gate: check a job posting URL before tailoring a CV.

Ported in spirit from career-ops (career-ops-hq/career-ops), whose liveness
gate stops a full evaluation on a dead link: a 404, expired or closed posting
must never consume a tailored CV, report and delivery checks.

Classification:
- live: HTTP 200, the expected role title appears on the page, the final URL
  still points at the posting, no closure phrase, and no application deadline
  that has already passed
- expired: HTTP 200 with an explicit application deadline before today (the form
  may still accept input; the candidate decides, but this is never "live")
- dead: HTTP 404/410, a closure phrase on a non-200 page, or the site
  redirected away from the posting path (typical for closed Greenhouse jobs)
- suspicious: everything else; the candidate decides, the script never guesses

Usage:
    python3 scripts/check_posting_liveness.py <url> \
        [--expect "Role Title"] [--timeout 20]

Exit 0 for live, 1 for dead/suspicious, 2 for tool errors. JavaScript-rendered
boards can hide closure notices from this check: a suspicious verdict on a
board you know renders client-side means verify in a browser before tailoring.
"""

import argparse
import datetime as _dt
import re
import sys
import urllib.request

CLOSURE_PHRASES = (
    "no longer accepting applications",
    "this job is no longer available",
    "this position has been filled",
    "position is no longer open",
    "the job you are looking for is no longer open",
    "job posting has expired",
    "this job is closed",
    "we are no longer hiring",
    "requisition has been closed",
    "posting is closed",
    "not accepting applications",
    "no longer open",
    "applications are closed",
    "the vacancy is no longer published",
    "ogłoszenie wygasło",
    "deze vacature is niet meer gepubliceerd",
    "oferta cerrada",
)
TRANSIENT_STATUSES = {429, 500, 502, 504}

# A job noun within 60 chars of "has been filled" is closure; "form has been
# filled out" is a candidate completing an application, not a closed req.
FILLED_RE = re.compile(
    r"\b(job|position|role|vacancy|requisition|opportunity)\b[^.!?\n]{0,60}"
    r"\bhas been filled\b(?!\s+out)", re.I)


def closure_detail(text):
    """Return a closure detail, or None. Question forms are not closure."""
    lowered = normalize(text)
    for phrase in CLOSURE_PHRASES:
        for match in re.finditer(re.escape(phrase), lowered):
            tail = lowered[match.end():match.end() + 12]
            if tail.lstrip().startswith("?"):
                continue
            return "closure phrase: %s" % phrase
    if FILLED_RE.search(text):
        return "closure phrase: job/position has been filled"
    return None


def find_deadline(text, today=None):
    """Extract an explicit application deadline date, if the page states one.

    Only deadline/apply-by phrasing counts. A yearless date resolves to the
    current year unless that would be more than 60 days in the past, in which
    case next year is used (a January deadline seen in November is next year).
    Returns (date, raw_match) or (None, None).
    """
    today = today or _dt.date.today()
    pattern = re.compile(
        r"(?:deadline(?:\s+for\s+(?:applying|applications))?|apply\s+by|"
        r"applications?\s+close)\s*(?:is|:|by)?\s*"
        r"([A-Z][a-z]+|\d{1,2})\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,?\s+(\d{4}))?", re.I)
    months = {name.lower(): index for index, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"), 1)}
    for match in pattern.finditer(text):
        month = months.get(match.group(1).lower())
        if not month:
            continue
        day, year = int(match.group(2)), match.group(3)
        if not 1 <= day <= 31:
            continue
        for candidate_year in ([int(year)] if year else
                               [today.year, today.year + 1]):
            try:
                deadline = _dt.date(candidate_year, month, day)
            except ValueError:
                continue
            if year or deadline >= today - _dt.timedelta(days=60):
                return deadline, match.group(0)
    return None, None


def normalize(text):
    return " ".join(text.split()).lower()


def classify(status, body, final_url, requested_url, expected, today=None,
             deadline_text=None):
    detailed = closure_detail(body)
    if status in TRANSIENT_STATUSES:
        return "suspicious", "transient HTTP %d; retry later, never expired" % status
    if status in (404, 410):
        return "dead", "HTTP %d" % status
    if detailed:
        return ("dead" if status != 200 else "suspicious"), detailed

    normalized_body = normalize(body)
    if expected and normalize(expected) not in normalized_body:
        return ("suspicious", "expected role title '%s' not found on the page"
                % expected)

    requested_path = re.sub(r"^https?://[^/]+", "", requested_url).split("?")[0]
    final_path = re.sub(r"^https?://[^/]+", "", final_url).split("?")[0]
    if requested_path != "/" and final_path != requested_path:
        return ("suspicious", "redirected from %s to %s"
                % (requested_path, final_path))

    if status == 200:
        deadline, _ = find_deadline(deadline_text or body, today=today)
        if deadline:
            today = today or _dt.date.today()
            detail = "HTTP 200, expected content present, deadline %s (%s)" % (
                deadline.isoformat(), "PASSED" if deadline < today else "open")
            if deadline < today:
                return "expired", detail
            return "live", detail
        return "live", "HTTP 200, expected content present"
    return "suspicious", "HTTP %d" % status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Job posting URL to check")
    parser.add_argument("--expect", default="",
                        help="Role title the live page should contain")
    parser.add_argument("--timeout", type=int, default=20,
                        help="Seconds before the check gives up (default 20)")
    parser.add_argument("--deadline", default="",
                        help="Deadline text read from a browser-rendered page, "
                             "e.g. 'November 20th'; JS-rendered boards can hide "
                             "it from the raw HTML fetch")
    args = parser.parse_args(argv)

    request = urllib.request.Request(
        args.url,
        headers={"User-Agent": "cv-witness liveness check",
                 "Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            status = response.status
            final_url = response.geturl()
            body = response.read(1024 * 1024).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        status, final_url, body = error.code, args.url, ""
    except (OSError, urllib.error.URLError) as error:
        print("suspicious: could not reach the posting (%s)" % error)
        sys.exit(1)

    deadline_text = ("deadline for applying is " + args.deadline) if args.deadline else None
    verdict, detail = classify(status, body, final_url, args.url, args.expect,
                               deadline_text=deadline_text)
    print("%s: %s" % (verdict, detail))
    sys.exit(0 if verdict == "live" else 1)


if __name__ == "__main__":
    main()
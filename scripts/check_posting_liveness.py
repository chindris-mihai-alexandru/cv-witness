"""Posting liveness gate: check a job posting URL before tailoring a CV.

Ported in spirit from career-ops (career-ops-hq/career-ops), whose liveness
gate stops a full evaluation on a dead link: a 404, expired or closed posting
must never consume a tailored CV, report and delivery checks.

Classification:
- live: HTTP 200, the expected role title appears on the page, the final URL
  still points at the posting, and no closure phrase is present
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
)


def normalize(text):
    return " ".join(text.split()).lower()


def classify(status, body, final_url, requested_url, expected):
    lowered = normalize(body)
    for phrase in CLOSURE_PHRASES:
        if phrase in lowered:
            detail = "closure phrase: %s" % phrase
            return ("dead" if status != 200 else "suspicious"), detail
    if status in (404, 410):
        return "dead", "HTTP %d" % status

    if expected and normalize(expected) not in lowered:
        return ("suspicious", "expected role title '%s' not found on the page"
                % expected)

    requested_path = re.sub(r"^https?://[^/]+", "", requested_url).split("?")[0]
    final_path = re.sub(r"^https?://[^/]+", "", final_url).split("?")[0]
    if requested_path != "/" and final_path != requested_path:
        return ("suspicious", "redirected from %s to %s"
                % (requested_path, final_path))

    if status == 200:
        return "live", "HTTP 200, expected content present"
    return "suspicious", "HTTP %d" % status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Job posting URL to check")
    parser.add_argument("--expect", default="",
                        help="Role title the live page should contain")
    parser.add_argument("--timeout", type=int, default=20,
                        help="Seconds before the check gives up (default 20)")
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

    verdict, detail = classify(status, body, final_url, args.url, args.expect)
    print("%s: %s" % (verdict, detail))
    sys.exit(0 if verdict == "live" else 1)


if __name__ == "__main__":
    main()
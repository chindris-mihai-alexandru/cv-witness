"""Numeric layout checks over `pdftotext -bbox-layout` output.

Pure functions: no tools are run and no CV text is echoed. Reports carry codes,
indices and point measurements only, so they are safe to print.
"""

from collections import Counter
import html
from statistics import median
import re
import unicodedata

PAGE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)
LINE = re.compile(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>', re.S)
WORD = re.compile(r'<word [^>]*>(.*?)</word>', re.S)
SAME_ROW_POINTS = 2.0


def normalized_text(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def parse_pages(bbox):
    """Pages of rows; a row joins the lines that share a baseline (title + right-aligned date)."""
    pages = []
    for width, height, body in PAGE.findall(bbox):
        lines = []
        for x0, y0, x1, y1, inner in LINE.findall(body):
            text = normalized_text(html.unescape(" ".join(WORD.findall(inner))))
            if text:
                lines.append({"x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1), "text": text})
        rows = []
        for line in sorted(lines, key=lambda item: (item["y0"], item["x0"])):
            centre = (line["y0"] + line["y1"]) / 2
            if rows and abs(centre - rows[-1]["centre"]) <= SAME_ROW_POINTS:
                rows[-1]["parts"].append(line)
            else:
                rows.append({"centre": centre, "parts": [line]})
        for row in rows:
            row["parts"].sort(key=lambda item: item["x0"])
            row["x0"] = row["parts"][0]["x0"]
            row["x1"] = max(part["x1"] for part in row["parts"])
            row["y0"] = min(part["y0"] for part in row["parts"])
            row["y1"] = max(part["y1"] for part in row["parts"])
            row["text"] = " ".join(part["text"] for part in row["parts"])
        pages.append({"width": float(width), "height": float(height), "rows": rows})
    return pages


def _matches(row, target):
    return row["text"] == target or row["text"].startswith(target + " ")


def _gaps_before(pages, targets, exact=False):
    """Gap above each matching row; rows that open a page have no measurable gap."""
    found, gaps = 0, []
    for page in pages:
        for index, row in enumerate(page["rows"]):
            if any(row["text"] == t if exact else _matches(row, t) for t in targets):
                found += 1
                if index:
                    gaps.append(row["y0"] - page["rows"][index - 1]["y1"])
    return found, gaps


def _gaps_after(pages, targets):
    gaps = []
    for page in pages:
        rows = page["rows"]
        for index, row in enumerate(rows[:-1]):
            if any(row["text"] == t for t in targets):
                gaps.append(rows[index + 1]["y0"] - row["y1"])
    return gaps


def _clusters(values, tolerance):
    result = []
    for value in sorted(values):
        if result and value - result[-1][-1] <= tolerance:
            result[-1].append(value)
        else:
            result.append([value])
    return result


def _body_rows(pages, headings):
    """Rows from the first heading onward; the centred header block is excluded."""
    wanted = {normalized_text(h) for h in headings}
    started, body = False, []
    for page in pages:
        for row in page["rows"]:
            started = started or row["text"] in wanted
            if started:
                body.append(row)
    return body


def check_layout(pages, headings=(), gap_groups=(), right_aligned=(), max_left_edges=2, tolerance=1.0):
    """Return problem dicts; an empty list means the geometry is consistent."""
    problems = []
    headings = [normalized_text(h) for h in headings]
    if headings:
        found, gaps = _gaps_before(pages, headings, exact=True)
        if found != len(headings):
            problems.append({"code": "layout_target_missing", "group": "headings"})
        if gaps and max(gaps) - min(gaps) > tolerance:
            problems.append({"code": "layout_uneven_gap", "group": "headings", "spread_pt": round(max(gaps) - min(gaps), 2)})
        after = _gaps_after(pages, headings)
        if after and max(after) - min(after) > tolerance:
            problems.append({"code": "layout_uneven_gap", "group": "after_headings", "spread_pt": round(max(after) - min(after), 2)})
        for page in pages:
            if page["rows"] and page["rows"][-1]["text"] in headings:
                problems.append({"code": "layout_orphan_heading"})
    for number, group in enumerate(gap_groups, 1):
        targets = [normalized_text(item) for item in group]
        found, gaps = _gaps_before(pages, targets)
        if found != len(targets):
            problems.append({"code": "layout_target_missing", "group": number})
        if gaps and max(gaps) - min(gaps) > tolerance:
            problems.append({"code": "layout_uneven_gap", "group": number, "spread_pt": round(max(gaps) - min(gaps), 2)})
    body = _body_rows(pages, headings)
    if body and len(_clusters([row["x0"] for row in body], tolerance)) > max_left_edges:
        problems.append({"code": "layout_left_edges", "found": len(_clusters([row["x0"] for row in body], tolerance)), "allowed": max_left_edges})
    dates = [normalized_text(item) for item in right_aligned]
    if dates and body:
        edges, others = [], []
        for row in body:
            for part in row["parts"]:
                (edges if any(part["text"].endswith(d) for d in dates) and part["x0"] > row["x0"] else others).append(part["x1"])
        if len(edges) < len(set(dates)) or not others:
            problems.append({"code": "layout_target_missing", "group": "right_aligned"})
        elif max(edges) - min(edges) > tolerance or abs(max(others) - max(edges)) > 2 * tolerance:
            problems.append({"code": "layout_right_edge", "date_spread_pt": round(max(edges) - min(edges), 2),
                             "text_vs_date_pt": round(max(others) - max(edges), 2)})
    return problems


def layout_metrics(pages, headings=()):
    """Comparable design fingerprint; used for approved-baseline comparison."""
    rows = [row for page in pages for row in page["rows"]]
    body = _body_rows(pages, headings) or rows
    pitches = [round(b["y0"] - a["y0"], 2) for page in pages for a, b in zip(page["rows"], page["rows"][1:])
               if abs(a["x0"] - b["x0"]) < .5 and 0 < b["y0"] - a["y0"] < 16]
    _, gaps = _gaps_before(pages, [normalized_text(h) for h in headings], exact=True)
    return {"left_margin_pt": min(row["x0"] for row in body), "right_edge_pt": max(row["x1"] for row in body),
            "top_pt": pages[0]["rows"][0]["y0"], "line_pitch_pt": Counter(pitches).most_common(1)[0][0] if pitches else None,
            "heading_gap_pt": median(gaps) if gaps else None}


BASELINE_TOLERANCE_PT = {"left_margin_pt": 2.5, "right_edge_pt": 2.5, "top_pt": 4.0, "line_pitch_pt": 1.0, "heading_gap_pt": 3.0}


def compare_baseline(candidate, reference):
    """Metric names and point deltas only; the approved design is never inferred from prose."""
    return [{"code": "baseline_deviation", "metric": name, "delta_pt": round(candidate[name] - reference[name], 2), "allowed_pt": allowed}
            for name, allowed in BASELINE_TOLERANCE_PT.items()
            if candidate.get(name) is not None and reference.get(name) is not None and abs(candidate[name] - reference[name]) > allowed]

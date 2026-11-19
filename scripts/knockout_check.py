#!/usr/bin/env python3
"""Knockout check: verify a CV against a posting's hard requirements.

Recruiters apply "knockout" filters before a human ever reads a resume: work
authorization, years of experience, location, education, required licences.
A missing knockout is an automatic archive, so it is worth checking before
tailoring rather than after.

This script is deterministic and read-only. It extracts candidate knockout
signals from a posting with conservative patterns, then looks for evidence in
the CV. It reports PASS / FAIL / UNCLEAR per signal, never a single verdict.

Usage:
    python3 scripts/knockout_check.py --posting posting.txt --cv CV.pdf
    python3 scripts/knockout_check.py --posting posting.txt --cv CV.pdf --json

Exit codes:
    0 - every extracted signal has evidence in the CV
    1 - at least one signal is FAIL or UNCLEAR
    2 - input or tool error
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


class KnockoutError(Exception):
    """Raised for input or tool failures."""


# --- posting signal extraction ---------------------------------------------

MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

EXPERIENCE_PATTERNS = [
    re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*years?", re.I),          # "4-6 years" (explicit range)
    re.compile(r"(\d+)\s*to\s*(\d+)\s*years?", re.I),            # "2 to 6 years"
    re.compile(r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?(?:professional\s+|relevant\s+|post[- ]?graduation\s+)?experience", re.I),
    re.compile(r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?experience\s+(?:in|with)", re.I),
    re.compile(r"experience\s*(?:of\s*)?(?:at\s+least\s*)?(\d+)\s*\+?\s*years?", re.I),
    re.compile(r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?(?:industry\s+|work\s+)?experience", re.I),
    # "3+ years system development, network operations, software support, IT
    # experience" - a noun list sits between the number and "experience".
    re.compile(r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?(?:prior\s+)?[a-z][a-z ,/&\-]{2,300}?experience", re.I),
]

EDUCATION_PATTERNS = [
    (re.compile(r"\b(ph\.?d\.?|doctorate|doctoral)\b", re.I), "PhD"),
    (re.compile(r"\bmaster'?s?\b|\bm\.?sc?\.?\b|\bm\.?eng\.?\b|\bmba\b", re.I), "Master's"),
    (re.compile(r"\bbachelor'?s?\b|\bb\.?a\.?\b|\bb\.?sc?\.?\b|\bb\.?eng\.?\b|\bundergraduate\s+degree\b", re.I), "Bachelor's"),
]

# "City, Country" / "City, State, Country" in a posting header. Spaces only —
# never newlines, so a header line cannot swallow the next line. The match is
# post-filtered in _first_place() to drop department-style fragments.
PLACE_RE = re.compile(
    r"\b([A-Z][A-Za-z.'-]+(?:[ \t]+[A-Z][A-Za-z.'-]+)?,[ \t]*[A-Z][A-Za-z.'-]+(?:[ \t]+[A-Z][A-Za-z.'-]+)?)\b"
)

# Acronym-like first words that mark department fragments ("AFC Ops, KYC Ops",
# "MLRO France, KYC France") rather than city names. Pure 1-4 cap words.
_ACRONYM_TOKEN = re.compile(r"^[A-Z]{1,4}$")

# Places whose official name includes an article; do not strip it.
_ARTICLE_NAME_EXCEPTIONS = {"the hague"}

# Job-title words that can precede a city in a header ("Backend Engineer
# Berlin, Germany"): drop them when they lead the first token.
_ROLE_PREFIX_WORDS = {
    "backend", "frontend", "software", "senior", "junior", "lead", "head",
    "principal", "staff", "engineer", "engineers", "developer", "developers",
    "manager", "managers", "consultant", "consultants", "analyst", "analysts",
    "specialist", "specialists", "director", "directors", "full", "stack",
    "cloud", "devops", "data", "ml", "ai", "platform", "infrastructure",
    "systems", "product", "project", "program", "programmer", "programmers",
    "architect", "architects", "scientist", "scientists", "ops", "technical",
    "intern", "trainee", "apprentice", "associate", "support", "test",
    "testing", "qa", "security", "network", "site", "reliability",
}


def _clean_place(raw: str) -> str | None:
    """Clean one PLACE_RE capture into "City, Country", or None for a fragment."""
    place = raw.strip()
    t1, _, t2 = place.partition(",")
    w1 = t1.strip().split()
    w2 = t2.strip().split()
    if not w1 or not w2:
        return None

    def has_acronym(words, limit=3):
        return any(_ACRONYM_TOKEN.match(w) for w in words[:limit])

    # Both halves starting with acronym-like tokens = department fragment.
    if has_acronym(w1) and has_acronym(w2):
        return None
    # Hyphenated job descriptors ("Full-time, Non-Investment") are not places.
    if any("-" in w for w in w1) or any("-" in w for w in w2):
        return None
    # Drop job-title prefixes from the first token, keeping at least one word.
    while len(w1) > 1 and w1[0].lower() in _ROLE_PREFIX_WORDS:
        w1 = w1[1:]
    cleaned = " ".join(w1) + ", " + " ".join(w2)
    # Strip a leading article unless the official name needs it ("The Hague").
    if " ".join(w1).lower() not in _ARTICLE_NAME_EXCEPTIONS:
        cleaned = re.sub(r"^(?:The|A|An)\s+", "", cleaned).strip()
    return cleaned or None


def _first_place(posting: str) -> str | None:
    """Return the best "City, Country" signal, or None.

    Filters PLACE_RE hits that are list fragments or acronym-pair department
    names, so "SAR, RFI and STR reporting" or "AFC Ops, KYC Ops team" do not
    masquerade as locations. Also strips job-title prefixes ("Backend
    Engineer Berlin, Germany" -> "Berlin, Germany").
    """
    header = BODY_HEADING_RE.split(posting, maxsplit=1)[0]
    m = PLACE_RE.search(header)
    if not m:
        return None
    # "City, Country and X" = a list continuation, not a location.
    if re.match(r"\s+(?:and|&|or)\s+[A-Za-z]", header[m.end():]):
        return None
    return _clean_place(m.group(1))

LOCATION_PATTERNS = [
    re.compile(r"\b(?:located\s+in|based\s+in|location\s*[:=]?)\s+([A-Z][A-Za-z .'-]{2,40})"),
    re.compile(r"\b(remote(?:\s+only)?|hybrid|on[- ]?site|in[- ]office)\b", re.I),
]

# A "locations: Aalborg, Copenhagen, Antwerp" header names every work location
# explicitly. PLACE_RE can only ever capture two comma-separated tokens, so this
# pattern is what makes multi-location postings readable.
LOCATION_LIST_RE = re.compile(
    r"\blocations?\s*[:=]\s*([A-Z][A-Za-z.'&/ ]+(?:,[ \t]*[A-Z][A-Za-z.'&/ ]+)*)"
)

# A posting's header carries the work location. Everything after the first
# body heading is duties and requirements, where "FTP, Postman" and
# "Java, SSO" are skill enumerations, not cities. Scoping place detection to
# the header avoids inventing locations from a requirements bullet.
BODY_HEADING_RE = re.compile(
    r"^\s*(?:requirements?|qualifications?|skills?|competencies|"
    r"tech(?:nology)?|tools?)\s*:|"
    r"^\s*(?:what you(?:['’]s|'ll| will|'re| are)?\s+"
    r"(?:be\s+)?(?:do(?:ing)?|need|bring|working\s+on)|"
    r"who (?:we|you)(?:['’]re| are)?\s+(?:looking\s+for|need)|"
    r"example projects?|day-to-day|about\b|"
    r"the role|position summary|responsibilities|nice to have|"
    r"benefits|who you are|what we offer|key responsibilities|"
    r"why (?:support|join|work|we)|what it.s like)",
    re.I | re.M,
)
SKILL_ENUM_RE = re.compile(
    r"\b(?:e\.g\.|such as|including|knowledge of|understanding of|"
    r"experience with|familiarity with|tools?|certifications?|plus)\b", re.I)
# Lever postings often put "Hungary - Budapest" in the header. Only accept the
# dash form when the first half is a known country name.
COUNTRY_DASH_RE = re.compile(
    r"^\s*([A-Z][A-Za-z ]{2,30}?)\s*[-–]\s*([A-Z][A-Za-z .'-]{2,30})\s*$", re.M)
# YC/Lever headers often say "Berlin, On-site" or "Berlin Office" instead of
# "Berlin, Germany". Resolve the known city to its country rather than leaving
# the role with no location at all.
CITY_MODE_RE = re.compile(
    r"^\s*([A-Z][A-Za-z .'-]{2,30})\s*,\s*(?:on[- ]?site|hybrid|remote|office)\b"
    r"|^\s*([A-Z][A-Za-z .'-]{2,30})\s+Office\b",
    re.I | re.M,
)
# Teamtailor-style headers put the city between middle dots, mid-line:
# "Platform Services · Rotterdam · Hybrid". Capture the city before the mode word.
CITY_DOT_MODE_RE = re.compile(
    r"[·•]\s*([A-Z][A-Za-z .'-]{2,30})\s*[·•]\s*(?:on[- ]?site|hybrid|remote|office)\b",
    re.I,
)

WORK_AUTH_PATTERNS = [
    re.compile(r"\b(?:must\s+be\s+)?authorized\s+to\s+work\s+(?:in|for)\s+([A-Za-z .'-]{2,40})", re.I),
    re.compile(r"\bright\s+to\s+work\s+(?:in|for)\s+([A-Za-z .'/-]{2,60})", re.I),
    re.compile(r"\bvisa\s+sponsorship\b", re.I),
    re.compile(r"\bwork\s+permit\b", re.I),
    re.compile(r"\bcitizenship\b", re.I),
]

# Security clearance is a hard gate: it is employer-sponsored, takes months and
# is only ever "active" if the candidate already holds it. A posting that
# requires it is a stop unless the candidate confirms they hold the level.
CLEARANCE_PATTERNS = [
    re.compile(r"\bactive\s+security\s+clearance\b", re.I),
    re.compile(r"\bsecurity\s+clearance\b", re.I),
    re.compile(r"\b(?:SC|DV|CTC|NATO)\s+clearance\b"),
    re.compile(r"\bdeveloped\s+vetting\b", re.I),
    re.compile(r"\bsecurity\s+cleared\b", re.I),
    re.compile(r"\bclearance\s+(?:is\s+)?(?:required|mandatory)\b", re.I),
]

# Country name -> ISO-3166-1 alpha-2. Only the names a posting header or a
# work-authorization sentence realistically uses.
COUNTRY_ISO2 = {
    "austria": "AT", "belgium": "BE", "bulgaria": "BG", "croatia": "HR",
    "cyprus": "CY", "czechia": "CZ", "czech republic": "CZ", "denmark": "DK",
    "estonia": "EE", "finland": "FI", "france": "FR", "germany": "DE",
    "greece": "GR", "hungary": "HU", "ireland": "IE", "italy": "IT",
    "latvia": "LV", "lithuania": "LT", "luxembourg": "LU", "malta": "MT",
    "netherlands": "NL", "poland": "PL", "portugal": "PT", "romania": "RO",
    "slovakia": "SK", "slovenia": "SI", "spain": "ES", "sweden": "SE",
    "iceland": "IS", "liechtenstein": "LI", "norway": "NO",
    "switzerland": "CH",
    "united kingdom": "GB", "uk": "GB", "england": "GB", "scotland": "GB",
    "wales": "GB", "northern ireland": "GB", "great britain": "GB",
    "united states": "US", "usa": "US", "canada": "CA", "australia": "AU",
}

# EU member states plus the EEA EFTA states and Switzerland (bilateral free
# movement with the EU). Citizens/residents of these can work in any other
# without a visa or sponsorship; the UK is deliberately absent (post-Brexit).
EU_EEA_FREE_MOVEMENT = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE", "IS", "LI", "NO", "CH",
}

# Work-mode words that restrict a "remote" role to a country or region.
REMOTE_RESTRICTED_RE = re.compile(
    r"\bremote\s+(?:in|within|from)\s+([A-Za-z .'/-]{2,60})", re.I
)

CERTIFICATION_PATTERNS = [
    re.compile(r"\b(certified|certification|certificate|license|licence)\s+(?:in\s+)?([A-Z][A-Za-z0-9 .+/#-]{2,40})"),
    re.compile(r"\b([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,4})\s+certification\s+(?:is\s+)?(?:required|preferred|mandatory)", re.I),
]


def read_text(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        raise KnockoutError(f"File not found: {path}")
    if p.suffix.lower() == ".pdf":
        try:
            r = subprocess.run(["pdftotext", "-layout", path, "-"],
                               capture_output=True, text=True, check=False)
        except OSError as e:
            raise KnockoutError(f"pdftotext failed: {e}") from e
        return r.stdout
    return p.read_text(encoding="utf-8", errors="replace")


# City -> ISO-3166-1 alpha-2 for the cities that appear in European posting
# headers ("Aalborg, Copenhagen, Antwerp" names cities, not countries). Only
# cities a candidate is plausibly targeting are listed; an unknown city stays
# UNCLEAR rather than being guessed.
CITY_COUNTRY = {
    # Denmark
    "aalborg": "DK", "copenhagen": "DK", "aarhus": "DK", "odense": "DK",
    "esbjerg": "DK", "roskilde": "DK",
    # Belgium
    "antwerp": "BE", "antwerpen": "BE", "brussels": "BE", "bruxelles": "BE",
    "ghent": "BE", "gent": "BE", "bruges": "BE", "liege": "BE", "leuven": "BE",
    "namur": "BE", "charleroi": "BE",
    # Netherlands
    "amsterdam": "NL", "rotterdam": "NL", "utrecht": "NL", "eindhoven": "NL",
    "groningen": "NL", "nijmegen": "NL", "tilburg": "NL", "almere": "NL",
    "the hague": "NL", "den haag": "NL", "haarlem": "NL", "leiden": "NL",
    "delft": "NL", "maastricht": "NL", "zwolle": "NL", "arnhem": "NL",
    # Germany
    "berlin": "DE", "munich": "DE", "munchen": "DE", "hamburg": "DE",
    "frankfurt": "DE", "cologne": "DE", "koln": "DE", "stuttgart": "DE",
    "dusseldorf": "DE", "dortmund": "DE", "essen": "DE", "leipzig": "DE",
    "dresden": "DE", "hanover": "DE", "hannover": "DE", "nuremberg": "DE",
    "nurnberg": "DE", "bremen": "DE", "bonn": "DE", "mannheim": "DE",
    "karlsruhe": "DE", "augsburg": "DE", "heidelberg": "DE", "freiburg": "DE",
    # France
    "paris": "FR", "lyon": "FR", "marseille": "FR", "toulouse": "FR",
    "bordeaux": "FR", "nantes": "FR", "lille": "FR", "strasbourg": "FR",
    "nice": "FR", "rennes": "FR", "grenoble": "FR", "montpellier": "FR",
    "dijon": "FR", "reims": "FR", "angers": "FR", "sophia antipolis": "FR",
    # United Kingdom
    "london": "GB", "manchester": "GB", "bristol": "GB", "birmingham": "GB",
    "edinburgh": "GB", "glasgow": "GB", "cardiff": "GB", "belfast": "GB",
    "cambridge": "GB", "oxford": "GB", "reading": "GB", "southampton": "GB",
    "gloucester": "GB", "cheltenham": "GB", "swindon": "GB", "york": "GB",
    "leeds": "GB", "liverpool": "GB", "newcastle": "GB", "sheffield": "GB",
    "nottingham": "GB", "leicester": "GB", "coventry": "GB", "bath": "GB",
    "brighton": "GB", "exeter": "GB", "canterbury": "GB", "winchester": "GB",
    "bristol": "GB", "plymouth": "GB", "norwich": "GB", "derby": "GB",
    "stevenage": "GB", "bracknell": "GB", "maidenhead": "GB", "slough": "GB",
    # Ireland
    "dublin": "IE", "cork": "IE", "galway": "IE", "limerick": "IE",
    "waterford": "IE", "kilkenny": "IE",
    # Spain
    "madrid": "ES", "barcelona": "ES", "valencia": "ES", "bilbao": "ES",
    "seville": "ES", "sevilla": "ES", "malaga": "ES", "zaragoza": "ES",
    "murcia": "ES", "palma": "ES", "san sebastian": "ES", "vigo": "ES",
    "gijon": "ES", "alicante": "ES", "granada": "ES",
    # Portugal
    "lisbon": "PT", "lisboa": "PT", "porto": "PT", "braga": "PT",
    "coimbra": "PT", "faro": "PT", "aveiro": "PT", "vilamoura": "PT",
    "funchal": "PT", "ponta delgada": "PT",
    # Italy
    "rome": "IT", "roma": "IT", "milan": "IT", "milano": "IT", "turin": "IT",
    "torino": "IT", "bologna": "IT", "florence": "IT", "firenze": "IT",
    "venice": "IT", "venezia": "IT", "naples": "IT", "napoli": "IT",
    "genoa": "IT", "genova": "IT", "verona": "IT", "padua": "IT",
    "padova": "IT", "trieste": "IT", "modena": "IT", "parma": "IT",
    "lucca": "IT", "siena": "IT", "bergamo": "IT", "brescia": "IT",
    # Austria
    "vienna": "AT", "wien": "AT", "salzburg": "AT", "innsbruck": "AT",
    "graz": "AT", "linz": "AT", "klagenfurt": "AT",
    # Switzerland
    "zurich": "CH", "zurich": "CH", "geneva": "CH", "geneve": "CH",
    "basel": "CH", "lausanne": "CH", "bern": "CH", "berne": "CH",
    "winterthur": "CH", "lucerne": "CH", "luzern": "CH", "st gallen": "CH",
    "st. gallen": "CH", "biel": "CH", "chur": "CH",
    # Sweden
    "stockholm": "SE", "gothenburg": "SE", "goteborg": "SE", "malmo": "SE",
    "malmo": "SE", "uppsala": "SE", "linkoping": "SE", "orebro": "SE",
    "vasteras": "SE", "lund": "SE", "helsingborg": "SE",
    # Norway
    "oslo": "NO", "bergen": "NO", "trondheim": "NO", "stavanger": "NO",
    "tromso": "NO", "drammen": "NO", "kristiansand": "NO",
    # Finland
    "helsinki": "FI", "espoo": "FI", "tampere": "FI", "turku": "FI",
    "oulu": "FI", "jyvaskyla": "FI", "lahti": "FI", "vaasa": "FI",
    # Poland
    "warsaw": "PL", "warszawa": "PL", "krakow": "PL", "wroclaw": "PL",
    "gdansk": "PL", "poznan": "PL", "lodz": "PL", "szczecin": "PL",
    "bydgoszcz": "PL", "lublin": "PL", "katowice": "PL",
    # Czechia
    "prague": "CZ", "praha": "CZ", "brno": "CZ", "ostrava": "CZ",
    "plzen": "CZ",
    # Hungary
    "budapest": "HU", "debrecen": "HU", "szeged": "HU",
    # Romania
    "bucharest": "RO", "bucuresti": "RO", "cluj-napoca": "RO", "cluj": "RO",
    "timisoara": "RO", "brasov": "RO", "iasi": "RO", "constanta": "RO",
    "sibiu": "RO", "oradea": "RO", "arad": "RO", "pitesti": "RO",
    "viseu de sus": "RO",
    # Bulgaria
    "sofia": "BG", "plovdiv": "BG", "varna": "BG", "burgas": "BG",
    # Croatia
    "zagreb": "HR", "split": "HR", "rijeka": "HR", "osijek": "HR",
    "zadar": "HR",
    # Slovenia
    "ljubljana": "SI", "maribor": "SI", "celje": "SI",
    # Slovakia
    "bratislava": "SK", "kosice": "SK",
    # Estonia
    "tallinn": "EE", "tartu": "EE",
    # Latvia
    "riga": "LV", "daugavpils": "LV",
    # Lithuania
    "vilnius": "LT", "kaunas": "LT", "klaipeda": "LT",
    # Greece
    "athens": "GR", "thessaloniki": "GR", "patras": "GR", "heraklion": "GR",
    # Cyprus
    "nicosia": "CY", "limassol": "CY", "larnaca": "CY",
    # Malta
    "valletta": "MT", "sliev": "MT",
    # Luxembourg
    "luxembourg": "LU", "esch-sur-alzette": "LU",
    # Iceland
    "reykjavik": "IS", "akureyri": "IS",
}

# Signals that carry profile data for the checkers rather than a requirement.
# They are extracted with the rest but never reported as a result row.
META_SIGNALS = {"work_auth_countries", "work_auth_sponsorship"}


def country_iso2(name: str) -> str | None:
    """Map a country or city name to ISO-3166-1 alpha-2."""
    if not name:
        return None
    key = re.sub(r"\s+", " ", name.strip().lower())
    key = re.sub(r"^(?:the|the\s+)", "", key).strip()
    if key in COUNTRY_ISO2:
        return COUNTRY_ISO2[key]
    if key in CITY_COUNTRY:
        return CITY_COUNTRY[key]
    # A multi-country list ("Denmark or the United Kingdom") - try each part.
    for part in re.split(r"\s*(?:,|/| or | and )\s*", key):
        part = part.strip()
        if part in COUNTRY_ISO2:
            return COUNTRY_ISO2[part]
        if part in CITY_COUNTRY:
            return CITY_COUNTRY[part]
    return None


def work_rights(citizen_iso2: str | None, target_name: str, sponsorship: bool = True) -> tuple[str, str]:
    """Evaluate whether a candidate may work in a country.

    Returns (status, detail). EU/EEA/Swiss freedom of movement is modelled
    explicitly: a Romanian citizen may work in Denmark without sponsorship,
    but not in the UK. Unknown countries are UNCLEAR, never a silent pass.
    """
    target = country_iso2(target_name)
    if target is None:
        return "UNCLEAR", f"unrecognised work-location '{target_name}'; confirm against the posting"
    if citizen_iso2 and target == citizen_iso2:
        return "PASS", f"{target_name} ({target}) is the candidate's own country"
    if citizen_iso2 and target in EU_EEA_FREE_MOVEMENT and citizen_iso2 in EU_EEA_FREE_MOVEMENT:
        return "PASS", f"EU/EEA free movement covers {target_name} ({target})"
    if sponsorship:
        return "UNCLEAR", f"{target_name} needs sponsorship; posting does not confirm it"
    return "FAIL", f"{target_name} is outside the candidate's free-movement area and no sponsorship is offered"


def extract_countries(text: str) -> list[str]:
    """Return country names present in a phrase, longest name first."""
    found = []
    lowered = text.lower()
    for name in sorted(COUNTRY_ISO2, key=len, reverse=True):
        if re.search(r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])", lowered):
            found.append(name)
    # Drop names that are substrings of a longer match already found.
    unique = []
    for name in found:
        if not any(name != other and name in other for other in found):
            unique.append(name)
    return unique


def extract_signals(posting: str) -> dict:
    """Extract candidate knockout signals from a posting. Conservative by design."""
    signals = {}

    # Years of experience. An explicit range ("4-6 years", "2 to 6 years") is a
    # precise requirement statement and wins over lone numbers, which often
    # come from the company's own tenure ("a firm with over 22 years of
    # experience"). Within one class, take the largest stated minimum.
    ranges = []
    for pat in EXPERIENCE_PATTERNS[:2]:
        for m in pat.finditer(posting):
            try:
                lo, hi = int(m.group(1)), int(m.group(2))
                if 0 < lo <= hi <= 60:
                    # "4-6 years" requires AT LEAST 4; the lower bound is the
                    # floor. The upper bound is a ceiling ("no more than"),
                    # not a minimum.
                    ranges.append(lo)
            except (ValueError, IndexError):
                continue
    if ranges:
        signals["min_years"] = max(ranges)
    else:
        years = []
        for pat in EXPERIENCE_PATTERNS[2:]:
            for m in pat.finditer(posting):
                try:
                    years.append((int(m.group(1)), m.start()))
                except (ValueError, IndexError):
                    continue
        # A lone decade-spanning number is usually the COMPANY's tenure, not a
        # candidate requirement ("a firm with over 22 years of experience").
        # No mainstream role requires 15+ years literally; drop such frames
        # unless the posting is explicitly senior-staff level.
        plausible = [(y, pos) for y, pos in years if y <= 15]
        if plausible:
            # "3+ years X OR 4+ years Y" are alternatives, not additive: the
            # candidate can satisfy either branch, so the floor is the
            # smallest. Without an "or" between mentions they stack, and the
            # largest stated minimum wins.
            alternatives = any(
                re.search(r"\bor\b", posting[plausible[i][1]:plausible[i + 1][1]], re.I)
                for i in range(len(plausible) - 1)
            )
            signals["min_years"] = (min(y for y, _ in plausible) if alternatives
                                    else max(y for y, _ in plausible))
        elif years and re.search(r"\b(?:senior|staff|principal|lead|head)\b", posting, re.I):
            # e.g. "requires 20+ years" for an explicitly stated senior-level role
            signals["min_years"] = max(y for y, _ in years)

    # Education floor. "Master's or PhD" means the floor is the lower degree;
    # "Master's and 5 years" still means Master's. Only take the highest when the
    # posting does not present the degrees as alternatives.
    mentioned = []
    for pat, label in EDUCATION_PATTERNS:
        if pat.search(posting):
            mentioned.append(label)
    if mentioned:
        rank = {"Bachelor's": 1, "Master's": 2, "PhD": 3}
        mentioned.sort(key=lambda x: rank.get(x, 0))
        floor = mentioned[0]
        # An explicit "or" between degree mentions marks an either/or floor.
        if len(mentioned) > 1 and re.search(
            r"\b" + re.escape(mentioned[-1]) + r"\b.{0,80}?\bor\b.{0,80}?\b" + re.escape(mentioned[0]) + r"\b",
            posting, re.I | re.S,
        ):
            floor = mentioned[0]
        elif len(mentioned) > 1:
            # "PhD ... or ... Master's" — the lower degree is the floor.
            floor = mentioned[0]
        signals["education"] = floor

    # Location: prefer a named place in the header over a work-mode word.
    place = _first_place(posting)
    if place:
        signals["location"] = place
    else:
        for pat in LOCATION_PATTERNS:
            m = pat.search(posting)
            if m:
                signals["location"] = m.group(0).strip()
                break

    # Work authorization. Keep the matched phrase AND the countries it names,
    # so the checker can reason about freedom of movement instead of stopping
    # at "confirm manually".
    for pat in WORK_AUTH_PATTERNS:
        m = pat.search(posting)
        if m:
            phrase = m.group(0).strip()
            signals["work_auth"] = phrase
            countries = extract_countries(m.group(1)) if m.lastindex else extract_countries(phrase)
            if countries:
                signals["work_auth_countries"] = countries
            signals["work_auth_sponsorship"] = bool(
                re.search(r"\b(?:no|not|without)\s+(?:any\s+)?(?:visa\s+)?sponsorship\b", posting, re.I)
                or re.search(r"\bsponsorship\s+(?:is\s+)?(?:not|unavailable)\b", posting, re.I)
            )
            break

    # Security clearance. A hard gate: it is employer-sponsored, takes months,
    # and "active" means already held.
    for pat in CLEARANCE_PATTERNS:
        m = pat.search(posting)
        if m:
            signals["clearance"] = m.group(0).strip()
            break

    # Every named place, not just the first: multi-location postings are common
    # ("Aalborg, Copenhagen, Antwerp") and the first-only signal loses the rest.
    places = []
    list_match = LOCATION_LIST_RE.search(posting)
    if list_match:
        places = [c.strip() for c in list_match.group(1).split(",") if c.strip()]
    if not places:
        header = BODY_HEADING_RE.split(posting, maxsplit=1)[0]
        # "Hungary - Budapest" style headers (common on Lever).
        for m in COUNTRY_DASH_RE.finditer(header):
            country, city = m.group(1).strip(), m.group(2).strip()
            if country.lower() in COUNTRY_ISO2:
                candidate = f"{city}, {country}"
                if candidate.lower() not in {p.lower() for p in places}:
                    places.append(candidate)
        # "Berlin, On-site" / "Berlin Office" style headers (common on YC).
        for m in CITY_MODE_RE.finditer(header):
            city = (m.group(1) or m.group(2)).strip()
            iso = CITY_COUNTRY.get(city.lower())
            if iso:
                candidate = f"{city}, {iso}"
                if candidate.lower() not in {p.lower() for p in places}:
                    places.append(candidate)
        # "Platform Services · Rotterdam · Hybrid" (middle-dot separators).
        for m in CITY_DOT_MODE_RE.finditer(header):
            city = m.group(1).strip()
            iso = CITY_COUNTRY.get(city.lower())
            if iso:
                candidate = f"{city}, {iso}"
                if candidate.lower() not in {p.lower() for p in places}:
                    places.append(candidate)
        for m in PLACE_RE.finditer(header):
            line_start = header.rfind("\n", 0, m.start()) + 1
            line_end = header.find("\n", m.start())
            line = header[line_start:line_end if line_end >= 0 else len(header)]
            # "e.g., FTP, Postman" is a tool list, never a work location.
            if SKILL_ENUM_RE.search(line):
                continue
            # "Azure, Citrix or infrastructure" is a list of alternatives, not a place.
            if re.match(r"\s+(?:and|&|or)\s+[A-Za-z]", header[m.end():]):
                continue
            candidate = _clean_place(m.group(1))
            if candidate and candidate.lower() not in {p.lower() for p in places}:
                places.append(candidate)
    if places:
        signals["locations"] = places
        # Keep `location` as a backwards-compatible alias for the first entry;
        # the report skips it when the full list is present.
        signals["location"] = places[0]

    # "Remote" in the title but restricted to a country in the body.
    remote_word = re.search(r"\bremote\b", posting[:200], re.I)
    restricted = REMOTE_RESTRICTED_RE.search(posting)
    if restricted:
        signals["remote_restricted"] = restricted.group(1).strip()
    elif remote_word and places:
        signals["remote_restricted"] = ", ".join(places)

    # Certifications
    certs = set()
    for pat in CERTIFICATION_PATTERNS:
        for m in pat.finditer(posting):
            label = (m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)).strip()
            if label and len(label) > 2:
                certs.add(label)
    if certs:
        signals["certifications"] = sorted(certs)

    return signals


# --- CV evidence matching ---------------------------------------------------

def years_from_cv(cv: str) -> list[int]:
    """Find explicit year counts in the CV (tenure spans, 'X years')."""
    found = []
    for m in re.finditer(r"(\d+)\s*\+?\s*years?\b", cv, re.I):
        try:
            n = int(m.group(1))
            if 0 < n <= 45:
                found.append(n)
        except ValueError:
            continue
    # Tenure spans like "Jul 2021 - Mar 2022" or "Nov 2022 - Apr 2025"
    for m in re.finditer(
        rf"({MONTHS}\s+\d{{4}})\s*[-–—]\s*({MONTHS}\s+\d{{4}}|present|current)",
        cv, re.I,
    ):
        try:
            start_match = re.search(r"\d{4}", m.group(1))
            end_match = re.search(r"\d{4}", m.group(2))
            if start_match is None:
                continue
            start = int(start_match.group(0))
            end = int(end_match.group(0)) if end_match else 2026
            span = end - start
            if 0 < span <= 45:
                found.append(span)
        except (ValueError, AttributeError):
            continue
    return found


def check_signal(name: str, value, cv: str, profile: dict | None = None) -> tuple[str, str]:
    """Return (status, detail) for one signal.

    ``profile`` carries candidate facts the checker cannot infer from the CV:
    citizenship/residency (ISO-3166-1 alpha-2) and whether the candidate already
    holds a security clearance. Absent a fact, the signal stays UNCLEAR.
    """
    cv_low = cv.lower()
    profile = profile or {}
    citizen = (profile.get("citizen") or profile.get("residency") or "").upper() or None
    sponsorship = profile.get("sponsorship", True)
    holds_clearance = bool(profile.get("holds_clearance"))

    if name == "min_years":
        spans = years_from_cv(cv)
        if not spans:
            return "UNCLEAR", f"posting requires {value}+ years; no year counts found in CV"
        total = max(spans)
        if total >= value:
            return "PASS", f"posting requires {value}+ years; CV shows up to {total}"
        return "FAIL", f"posting requires {value}+ years; CV shows max {total}"

    if name == "education":
        rank = {"Bachelor's": 1, "Master's": 2, "PhD": 3}
        cv_evidence = None
        for pat, label in EDUCATION_PATTERNS:
            if pat.search(cv):
                cv_evidence = label
                break
        if cv_evidence is None:
            return "UNCLEAR", f"posting requires {value}; no degree found in CV"
        if rank.get(cv_evidence, 0) >= rank.get(value, 0):
            return "PASS", f"posting requires {value}; CV shows {cv_evidence}"
        return "FAIL", f"posting requires {value}; CV shows {cv_evidence}"

    if name == "location":
        loc = str(value)
        # Remote/hybrid/onsite signals
        if loc.lower() in ("remote", "remote only", "hybrid", "on-site", "onsite", "in-office"):
            if loc.lower() in ("remote", "remote only"):
                return "UNCLEAR", "posting is remote; confirm work location matches"
            return "UNCLEAR", f"posting is {loc}; confirm work location matches"
        # Named place: look for it in the CV
        key = loc.strip().split(",")[0].strip().lower()
        if key and key in cv_low:
            return "PASS", f"posting location '{loc}' appears in CV"
        return "UNCLEAR", f"posting location '{loc}' not found in CV"

    if name == "work_auth":
        countries = profile.get("work_auth_countries") or []
        if not countries:
            return "UNCLEAR", "work authorization wording found; no country extracted, confirm manually"
        verdicts = []
        for country in countries:
            verdicts.append(work_rights(citizen, country, sponsorship))
        # One viable country is enough: "Denmark or the United Kingdom" passes if
        # the candidate may work in either. A country that needs sponsorship and
        # is explicitly refused still fails on its own.
        if any(v[0] == "PASS" for v in verdicts):
            return "PASS", "; ".join(v[1] for v in verdicts if v[0] == "PASS")
        if any(v[0] == "FAIL" for v in verdicts):
            return "FAIL", "; ".join(v[1] for v in verdicts if v[0] == "FAIL")
        return "UNCLEAR", "; ".join(v[1] for v in verdicts)

    if name == "clearance":
        if holds_clearance:
            return "PASS", "candidate confirms an active clearance"
        return "FAIL", f"posting requires '{value}'; clearance is employer-sponsored, takes months and must already be held"

    if name == "locations":
        places = [str(p) for p in (value or [])]
        if not places:
            return "UNCLEAR", "no work locations extracted"
        if citizen:
            results = []
            for place in places:
                country = extract_countries(place)
                target = country[0] if country else place
                results.append((place,) + work_rights(citizen, target, sponsorship))
            if any(r[1] == "PASS" for r in results):
                return "PASS", "workable: " + ", ".join(
                    f"{r[0]} ({r[2]})" for r in results if r[1] == "PASS"
                )
            if all(r[1] == "FAIL" for r in results):
                return "FAIL", "no workable location among: " + ", ".join(r[0] for r in results)
            return "UNCLEAR", "; ".join(f"{r[0]}: {r[2]}" for r in results)
        return "UNCLEAR", "candidate citizenship/residency unknown; cannot evaluate work rights"

    if name == "remote_restricted":
        return "CONFIRM", f"role is remote but restricted to: {value}"

    if name == "certifications":
        missing = [c for c in value if c.lower() not in cv_low]
        if not missing:
            return "PASS", f"all {len(value)} certification signal(s) found in CV"
        if len(missing) == len(value):
            return "FAIL", f"none of {value} found in CV"
        return "UNCLEAR", f"{len(missing)} of {len(value)} certification signal(s) not found: {missing}"

    return "UNCLEAR", "no checker for this signal"


def main() -> int:
    ap = argparse.ArgumentParser(description="Check a CV against a posting's hard requirements")
    ap.add_argument("--posting", required=True, help="Posting text file or URL-sourced text")
    ap.add_argument("--cv", required=True, help="CV file (PDF or text)")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    ap.add_argument("--citizen", help="Candidate citizenship (ISO-3166-1 alpha-2), e.g. RO")
    ap.add_argument("--residency", help="Candidate residency (ISO-3166-1 alpha-2); used when citizenship is unknown")
    ap.add_argument("--sponsorship", choices=["yes", "no"], default="yes",
                    help="Whether the candidate could use employer visa sponsorship (default yes)")
    ap.add_argument("--holds-clearance", action="store_true",
                    help="Candidate already holds an active security clearance")
    args = ap.parse_args()

    try:
        posting = read_text(args.posting)
        cv = read_text(args.cv)
    except KnockoutError as e:
        print(f"knockout-check: {e}", file=sys.stderr)
        return 2

    signals = extract_signals(posting)
    profile = {
        "citizen": args.citizen or args.residency,
        "residency": args.residency,
        "sponsorship": args.sponsorship == "yes",
        "holds_clearance": args.holds_clearance,
    }
    profile["work_auth_countries"] = signals.get("work_auth_countries", [])
    if signals.get("work_auth_sponsorship") is False:
        profile["sponsorship"] = False

    if not signals:
        msg = "No knockout signals extracted from the posting; nothing to check."
        if args.json:
            print(json.dumps({"signals": {}, "results": [], "profile": profile}, indent=2))
        else:
            print(msg)
        return 0

    results = []
    for name, value in signals.items():
        if name in META_SIGNALS:
            continue
        if name == "location" and "locations" in signals:
            continue  # the full list is reported instead of the alias
        status, detail = check_signal(name, value, cv, profile)
        results.append({"signal": name, "requirement": value, "status": status, "detail": detail})

    # A CONFIRM is a question to answer, not a pass: it never fails the run but
    # it must stay visible in the summary line.
    blocking = [r for r in results if r["status"] in ("FAIL", "UNCLEAR")]
    confirms = [r for r in results if r["status"] == "CONFIRM"]
    verdict = "STOP" if any(r["status"] == "FAIL" for r in results) else (
        "CONFIRM" if (blocking or confirms) else "PROCEED"
    )

    if args.json:
        print(json.dumps({"signals": signals, "profile": profile, "results": results, "verdict": verdict},
                         indent=2, ensure_ascii=False))
    else:
        print(f"=== KNOCKOUT CHECK ({len(results)} signal(s)) ===")
        for r in results:
            mark = r["status"]
            print(f"  [{mark}] {r['signal']}: {r['detail']}")
        print(f"  VERDICT: {verdict}")

    if any(r["status"] in ("FAIL", "UNCLEAR") for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

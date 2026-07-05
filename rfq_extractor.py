"""
V2 RFQ extractor.

This file receives already-extracted text from app.py and converts it into
structured project information for the proposal tool.

It avoids loose regex extraction where possible and only accepts address-like
text when it looks like a real street address.
"""

import re
from typing import Any, Dict, List, Optional


VICTORIAN_LOCALITIES = [
    "Avalon", "Bendigo", "Melbourne", "Geelong", "Ballarat", "Shepparton",
    "Echuca", "Mildura", "Wodonga", "Warrnambool", "Horsham", "Sale",
]


ADDRESS_WORDS = [
    "road", "rd", "street", "st", "avenue", "ave", "drive", "dr",
    "court", "ct", "crescent", "cres", "lane", "ln", "place", "pl",
    "highway", "hwy", "parade", "pde", "way", "boulevard", "blvd",
]


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line or "").strip()
    line = line.strip(" -:|•\t")
    return line


def lines_from_text(text: str) -> List[str]:
    return [clean_line(line) for line in clean_text(text).splitlines() if clean_line(line)]


def first_match(patterns: List[str], text: str) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = clean_line(match.group(1))
            if value:
                return value
    return None


def looks_like_street_address(value: str) -> bool:
    if not value:
        return False

    value_l = value.lower()

    has_number = bool(re.search(r"\b\d{1,6}[a-zA-Z]?\b", value))
    has_road_word = any(re.search(rf"\b{re.escape(word)}\b", value_l) for word in ADDRESS_WORDS)

    too_long = len(value) > 120
    bad_phrases = [
        "specific data",
        "soil and landscape",
        "background",
        "scope",
        "proposal",
        "deliverables",
        "methodology",
        "assessment",
    ]

    if any(phrase in value_l for phrase in bad_phrases):
        return False

    return has_number and has_road_word and not too_long


def extract_site_address(full_text: str) -> str:
    text = clean_text(full_text)
    lines = lines_from_text(text)

    labelled_patterns = [
        r"(?:site address|property address|subject site|site location|project address|location)\s*[:\-|]\s*(.+)",
        r"(?:address)\s*[:\-|]\s*(.+)",
    ]

    labelled = first_match(labelled_patterns, text)
    if labelled and looks_like_street_address(labelled):
        return labelled

    street_pattern = re.compile(
        r"\b\d{1,6}[A-Za-z]?\s+[A-Za-z0-9 '\-]+?\s+"
        r"(?:Road|Rd|Street|St|Avenue|Ave|Drive|Dr|Court|Ct|Crescent|Cres|Lane|Ln|Place|Pl|Highway|Hwy|Parade|Pde|Way|Boulevard|Blvd)"
        r"(?:,\s*[A-Za-z '\-]+)?(?:\s+VIC)?(?:\s+\d{4})?",
        re.IGNORECASE,
    )

    candidates = []

    for line in lines:
        for match in street_pattern.finditer(line):
            candidate = clean_line(match.group(0))
            if looks_like_street_address(candidate):
                candidates.append(candidate)

    if candidates:
        return max(candidates, key=len)

    return ""


def extract_project_title(full_text: str) -> str:
    text = clean_text(full_text)

    patterns = [
        r"(?:project title|project name)\s*[:\-|]\s*(.+)",
        r"(?:re|subject)\s*[:\-|]\s*(.+)",
    ]

    matched = first_match(patterns, text)
    if matched and len(matched) <= 160:
        return matched

    address = extract_site_address(text)
    if address:
        return f"{address} - Hydrological Engineering Services"

    for line in lines_from_text(text):
        if line.startswith("--- Source file:"):
            continue
        if 8 <= len(line) <= 160:
            return line

    return "Untitled Project"


def extract_project_type(full_text: str) -> str:
    text_l = clean_text(full_text).lower()

    if "industrial subdivision" in text_l:
        return "Industrial subdivision"
    if "residential subdivision" in text_l:
        return "Residential subdivision"
    if "subdivision" in text_l:
        return "Subdivision"
    if "development plan overlay" in text_l or "dpo" in text_l:
        return "Development planning / hydrological assessment"
    if "stormwater management" in text_l:
        return "Stormwater management assessment"
    if "flood" in text_l:
        return "Flood assessment"
    if "hydrological" in text_l or "hydrology" in text_l:
        return "Hydrological engineering services"

    return "Engineering services"


def extract_background(full_text: str) -> str:
    text = clean_text(full_text)

    section_patterns = [
        r"(?:project background|background|introduction|project overview|overview)\s*[:\n]\s*(.+?)(?=\n\s*(?:scope|services|deliverables|methodology|phase|requirements|fees|program|timeline)\b|\Z)",
        r"(?:development description|project description)\s*[:\n]\s*(.+?)(?=\n\s*(?:scope|services|deliverables|methodology|phase|requirements|fees|program|timeline)\b|\Z)",
    ]

    for pattern in section_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip()
            if len(value) > 40:
                return value[:1200]

    useful_lines = []
    keywords = [
        "proposed", "development", "subdivision", "site", "planning",
        "hydrological", "stormwater", "flood", "phase", "overlay",
    ]

    for line in lines_from_text(text):
        line_l = line.lower()
        if any(k in line_l for k in keywords) and len(line) > 40:
            useful_lines.append(line)
        if len(useful_lines) >= 5:
            break

    if useful_lines:
        return " ".join(useful_lines)[:1200]

    return ""


def extract_scope_summary(full_text: str) -> str:
    text = clean_text(full_text)

    match = re.search(
        r"(?:scope of works|scope|services required|required services)\s*[:\n]\s*(.+?)(?=\n\s*(?:deliverables|phase|fees|program|timeline|submission|requirements)\b|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if match:
        value = re.sub(r"\s+", " ", match.group(1)).strip()
        if len(value) > 30:
            return value[:1200]

    project_type = extract_project_type(text)
    return f"{project_type} based on the RFQ documentation."


def extract_phases(full_text: str) -> List[Dict[str, Any]]:
    text = clean_text(full_text)
    lines = lines_from_text(text)

    phases = []
    current_phase = None

    phase_heading = re.compile(r"^(phase\s*\d+[^\n:]*)(?:[:\-])?", re.IGNORECASE)

    for line in lines:
        heading = phase_heading.match(line)

        if heading:
            if current_phase:
                phases.append(current_phase)

            current_phase = {
                "phase_name": clean_line(heading.group(1)),
                "deliverables": [],
            }

            remainder = clean_line(line[heading.end():])
            if remainder:
                current_phase["deliverables"].append(remainder)

            continue

        if current_phase:
            is_useful = (
                len(line) > 8
                and not line.lower().startswith(("page ", "figure ", "table "))
            )

            if is_useful and len(current_phase["deliverables"]) < 10:
                current_phase["deliverables"].append(line)

    if current_phase:
        phases.append(current_phase)

    if phases:
        return phases[:8]

    deliverables = extract_deliverables(text)
    if deliverables:
        return [{"phase_name": "Scope of Works", "deliverables": deliverables}]

    return []


def extract_deliverables(full_text: str) -> List[str]:
    text = clean_text(full_text)
    lines = lines_from_text(text)

    deliverables = []
    keywords = [
        "prepare", "undertake", "review", "develop", "provide", "assess",
        "model", "calculate", "document", "report", "meeting", "submission",
    ]

    for line in lines:
        line_l = line.lower()
        if any(line_l.startswith(k) or f" {k} " in line_l for k in keywords):
            if 15 <= len(line) <= 220 and line not in deliverables:
                deliverables.append(line)

        if len(deliverables) >= 12:
            break

    return deliverables


def extract_authority_requirements(full_text: str) -> List[str]:
    lines = lines_from_text(full_text)

    keywords = [
        "planning scheme", "development plan overlay", "dpo", "council",
        "authority", "melbourne water", "cma", "catchment management",
        "stormwater management", "flood", "sbo", "lsio", "fo",
        "australian rainfall and runoff", "arr2019",
    ]

    results = []

    for line in lines:
        line_l = line.lower()
        if any(k in line_l for k in keywords):
            if 15 <= len(line) <= 260 and line not in results:
                results.append(line)

        if len(results) >= 12:
            break

    return results


def extract_contact(full_text: str) -> Dict[str, str]:
    text = clean_text(full_text)

    contact = {
        "name": "",
        "email": "",
        "phone": "",
        "company": "",
    }

    email = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    if email:
        contact["email"] = email.group(0)

    phone = re.search(r"(?:\+?61|0)[\d\s().-]{8,}\d", text)
    if phone:
        contact["phone"] = clean_line(phone.group(0))

    name = first_match(
        [
            r"(?:contact person|contact name|attention|attn)\s*[:\-|]\s*(.+)",
            r"(?:prepared by|request from)\s*[:\-|]\s*(.+)",
        ],
        text,
    )
    if name and len(name) <= 80:
        contact["name"] = name

    company = first_match(
        [
            r"(?:company|organisation|organization|client)\s*[:\-|]\s*(.+)",
        ],
        text,
    )
    if company and len(company) <= 120:
        contact["company"] = company

    return contact


def extract_rfq_data(full_text: str) -> Dict[str, Any]:
    text = clean_text(full_text)

    site_address = extract_site_address(text)
    project_title = extract_project_title(text)

    extraction_notes = []

    if not site_address:
        extraction_notes.append("No reliable street address was found in the RFQ text.")

    background = extract_background(text)
    if not background:
        extraction_notes.append("No clear project background section was found.")

    phases = extract_phases(text)
    if not phases:
        extraction_notes.append("No clear phases or deliverables were found.")

    return {
        "project_title": project_title,
        "site_address": site_address,
        "site_location": site_address,
        "project_address": site_address,
        "location": site_address,
        "project_type": extract_project_type(text),
        "scope_summary": extract_scope_summary(text),
        "background": background,
        "phases": phases,
        "deliverables": extract_deliverables(text),
        "authority_requirements": extract_authority_requirements(text),
        "contact": extract_contact(text),
        "extraction_notes": extraction_notes,
        "full_text": text,
    }

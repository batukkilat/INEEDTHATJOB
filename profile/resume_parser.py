"""
Rule-based resume parser for ATS-formatted resumes.
Handles: section headers in ALL CAPS, numbered bullets, TITLE – COMPANY | dates format.
"""
import re

_MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

_SECTION_HEADERS = {
    "SKILLS", "TECHNICAL SKILLS", "CORE SKILLS", "KEY SKILLS",
    "EXPERIENCE", "WORK EXPERIENCE", "PROFESSIONAL EXPERIENCE",
    "EDUCATION",
    "CERTIFICATIONS", "CERTIFICATION", "LICENSES",
    "PROJECTS", "KEY PROJECTS", "PERSONAL PROJECTS",
    "SUMMARY", "PROFILE", "OBJECTIVE",
    "ACHIEVEMENTS", "AWARDS", "LANGUAGES",
}


def _parse_date(s: str) -> str | None:
    if not s:
        return None
    s = s.strip()
    if s.lower() in ("present", "now", "current", "-", ""):
        return None
    # "Nov 2025" or "November 2025"
    m = re.match(r"([A-Za-z]+)\s+(\d{4})", s)
    if m:
        mon = _MONTHS.get(m.group(1).lower()[:3])
        return f"{m.group(2)}-{mon}" if mon else m.group(2)
    # "2024" only
    m = re.match(r"^(\d{4})$", s)
    if m:
        return m.group(1)
    # "2019–2024" or "2019-2024" (used in education dates inline)
    m = re.match(r"(\d{4})[–\-](\d{4})", s)
    if m:
        return m.group(1)
    return None


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "HEADER"
    sections[current] = []
    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()
        if upper in _SECTION_HEADERS:
            current = upper
            sections[current] = []
        else:
            sections.setdefault(current, []).append(stripped)
    return sections


def _rejoin_wrapped(lines: list[str]) -> list[str]:
    """Merge continuation lines (no leading digit/bullet) into the previous line."""
    result: list[str] = []
    for line in lines:
        if line and result and not re.match(r"^[\d•\-\*]", line):
            result[-1] = result[-1] + " " + line
        else:
            result.append(line)
    return result


def _split_outside_parens(s: str) -> list[str]:
    """Split on commas/semicolons that are not inside parentheses."""
    parts, current, depth = [], [], 0
    for ch in s:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch in ",;" and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def _clean_bullet(line: str) -> str:
    # Remove leading number + space, or bullet chars
    return re.sub(r"^[\d]+\s+|^[•\-\*]\s*", "", line).strip()


def _parse_skills(lines: list[str]) -> list[dict]:
    lines = _rejoin_wrapped(lines)
    skills = []
    _CATEGORY_MAP = {
        "language": "language", "languages": "language",
        "database": "technical", "databases": "technical",
        "big data": "technical", "tools": "technical", "devops": "technical",
        "visualization": "technical", "data engineering": "technical",
        "soft": "soft", "domain": "domain",
    }
    for line in lines:
        line = _clean_bullet(line)
        if not line:
            continue
        # "Category: item1, item2, ..."
        m = re.match(r"^(.+?):\s*(.+)$", line)
        if m:
            cat_raw = m.group(1).strip().lower()
            items = [i.strip() for i in _split_outside_parens(m.group(2)) if i.strip()]
            cat = "technical"
            for key, val in _CATEGORY_MAP.items():
                if key in cat_raw:
                    cat = val
                    break
            for item in items:
                if item:
                    skills.append({"name": item, "category": cat, "keywords": item})
        else:
            # plain skill name
            for item in re.split(r"[,;]", line):
                item = item.strip()
                if item:
                    skills.append({"name": item, "category": "technical", "keywords": item})
    return skills


_EXP_HEADER = re.compile(
    r"^(.+?)\s*[–\-]\s*(.+?)\s*\|\s*([A-Za-z]+\s+\d{4}|\d{4})\s*[–\-]\s*([A-Za-z\s\d]+)$"
)


def _parse_experience(lines: list[str]) -> list[dict]:
    experiences = []
    current: dict | None = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = _EXP_HEADER.match(line)
        if m:
            if current:
                experiences.append(current)
            current = {
                "title": m.group(1).strip(),
                "company": m.group(2).strip(),
                "start_date": _parse_date(m.group(3).strip()) or "",
                "end_date": _parse_date(m.group(4).strip()),
                "location": "Indonesia",
                "description": "",
                "is_remote": False,
                "achievements": [],
            }
            continue

        if current is not None:
            bullet = _clean_bullet(line)
            if bullet:
                # Merge wrapped bullet continuations into the previous achievement
                if current["achievements"] and not re.match(r"^[\d•\-\*]", line):
                    current["achievements"][-1]["description"] += " " + bullet
                else:
                    current["achievements"].append({"description": bullet, "metrics": "", "skills_used": ""})

    if current:
        experiences.append(current)
    return experiences


def _parse_education(lines: list[str]) -> list[dict]:
    education = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # "Bachelor of Science – Institution (2019–2024)"
        # "Degree – Institution (YYYY–YYYY)" or "Degree – Institution"
        m = re.match(r"^(.+?)\s*[–\-]\s*(.+?)(?:\s*\((\d{4})[–\-](\d{4})\))?$", line)
        if m:
            degree = m.group(1).strip()
            institution = m.group(2).strip()
            start = f"{m.group(3)}-01" if m.group(3) else None
            end = f"{m.group(4)}-12" if m.group(4) else None
            if institution and degree:
                education.append({
                    "institution": institution,
                    "degree": degree,
                    "field": "",
                    "start_date": start,
                    "end_date": end,
                    "gpa": None,
                })
    return education


def _parse_certifications(lines: list[str]) -> list[dict]:
    certs = []
    for line in lines:
        line = _clean_bullet(line).strip()
        if not line:
            continue
        # "Name – Issuer (YYYY)" or "Name – Issuer"
        m = re.match(r"^(.+?)\s*[–\-]\s*(.+?)(?:\s*\((\d{4})\))?$", line)
        if m:
            certs.append({
                "name": m.group(1).strip(),
                "issuer": m.group(2).strip(),
                "date_obtained": f"{m.group(3)}-01" if m.group(3) else None,
                "expiry_date": None,
            })
        else:
            certs.append({"name": line, "issuer": "", "date_obtained": None, "expiry_date": None})
    return certs


def _parse_projects(lines: list[str]) -> list[dict]:
    lines = _rejoin_wrapped(lines)
    projects = []
    for line in lines:
        line = _clean_bullet(line).strip()
        if not line:
            continue
        # "Project Name – description" or just "Project Name"
        m = re.match(r"^(.+?)\s*[–\-]\s*(.+)$", line)
        if m:
            projects.append({
                "name": m.group(1).strip(),
                "description": m.group(2).strip(),
                "url": "",
                "skills_used": "",
                "highlights": "",
            })
        else:
            projects.append({
                "name": line,
                "description": "",
                "url": "",
                "skills_used": "",
                "highlights": "",
            })
    return projects


def parse_resume_text(text: str) -> dict:
    lines = text.splitlines()
    sections = _split_sections(lines)

    skills = _parse_skills(
        sections.get("TECHNICAL SKILLS", []) +
        sections.get("SKILLS", []) +
        sections.get("CORE SKILLS", []) +
        sections.get("KEY SKILLS", [])
    )

    experiences = _parse_experience(
        sections.get("EXPERIENCE", []) +
        sections.get("WORK EXPERIENCE", []) +
        sections.get("PROFESSIONAL EXPERIENCE", [])
    )

    education = _parse_education(sections.get("EDUCATION", []))

    certifications = _parse_certifications(
        sections.get("CERTIFICATIONS", []) +
        sections.get("CERTIFICATION", []) +
        sections.get("LICENSES", [])
    )

    projects = _parse_projects(
        sections.get("KEY PROJECTS", []) +
        sections.get("PROJECTS", []) +
        sections.get("PERSONAL PROJECTS", [])
    )

    return {
        "skills": skills,
        "experiences": experiences,
        "education": education,
        "certifications": certifications,
        "projects": projects,
    }

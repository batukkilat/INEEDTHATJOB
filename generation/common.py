"""Shared helpers for the generation phase: prompt loading, profile JSON, language/company detection."""
import re
from functools import lru_cache
from pathlib import Path

from sqlmodel import Session

_PROMPT_DIR = Path("generation/prompts")

# Leading conversational wrappers chatty models prepend (e.g. "Here's the cover letter:")
_PREAMBLE_RE = re.compile(
    r"^\s*(here('?s| is)|sure|certainly|of course|absolutely|below is|"
    r"i('?ve| have) (written|drafted|created|prepared)|i('?d| would) be happy)"
    r"[^\n]*?(:\s*\n|\.\s*\n|\n)",
    re.IGNORECASE,
)
# Trailing offers (e.g. "Let me know if you'd like any changes.")
_POSTAMBLE_RE = re.compile(
    r"\n+\s*(let me know|feel free|i hope this|hope this helps|please let me know)"
    r"[^\n]*$",
    re.IGNORECASE,
)


@lru_cache(maxsize=None)
def load_prompt(filename: str) -> str:
    return (_PROMPT_DIR / filename).read_text()


def strip_preamble(text: str) -> str:
    """Remove conversational wrapper lines a chatty LLM adds around generated content."""
    text = _PREAMBLE_RE.sub("", text)
    text = _POSTAMBLE_RE.sub("", text)
    return text.strip()


def detect_language(text: str) -> str:
    indonesian_markers = ["kami", "anda", "untuk", "dengan", "dalam", "adalah",
                          "yang", "di ", "dan ", "atau ", "dari ", "pada "]
    text_lower = text.lower()
    hits = sum(1 for m in indonesian_markers if m in text_lower)
    return "Indonesian" if hits >= 3 else "English"


def company_type(company: str) -> str:
    company_lower = company.lower()
    if any(w in company_lower for w in ["startup", "tech", "labs", "studio"]):
        return "startup"
    if any(w in company_lower for w in ["bank", "finance", "tbk", "pt."]):
        return "corporate"
    return "professional"


def build_profile_json(session: Session) -> dict:
    import profile.service as svc
    skills = [{"name": s.name, "category": s.category, "proficiency": s.proficiency,
               "years_experience": s.years_experience, "keywords": s.keywords}
              for s in svc.get_skills(session)]
    experiences = []
    for exp in svc.get_experiences(session):
        achievements = svc.get_achievements(session, exp.id)
        experiences.append({
            "company": exp.company,
            "title": exp.title,
            "start_date": exp.start_date or "",
            "end_date": exp.end_date or "Present",
            "location": exp.location or "",
            "description": exp.description or "",
            "achievements": [{"description": a.description, "metrics": a.metrics,
                              "skills_used": a.skills_used}
                             for a in achievements],
        })
    education = [{"institution": e.institution, "degree": e.degree,
                  "field": e.field or "", "start_date": e.start_date or "", "end_date": e.end_date or "Present",
                  "gpa": e.gpa or ""}
                 for e in svc.get_education_list(session)]
    certifications = [{"name": c.name, "issuer": c.issuer or "", "date_obtained": c.date_obtained or ""}
                      for c in svc.get_certifications(session)]
    projects = [{"name": p.name, "description": p.description or "",
                 "skills_used": p.skills_used or "", "highlights": p.highlights or ""}
                for p in svc.get_projects(session)]
    return {"skills": skills, "experiences": experiences, "education": education,
            "certifications": certifications, "projects": projects}

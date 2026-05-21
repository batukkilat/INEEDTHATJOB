"""Shared helpers for the generation phase: prompt loading, profile JSON, language/company detection."""
from functools import lru_cache
from pathlib import Path

from sqlmodel import Session

_PROMPT_DIR = Path("generation/prompts")


@lru_cache(maxsize=None)
def load_prompt(filename: str) -> str:
    return (_PROMPT_DIR / filename).read_text()


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
    skills = [{"name": s.name, "category": s.category, "proficiency": s.proficiency}
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
            "achievements": [{"description": a.description, "metrics": a.metrics}
                             for a in achievements],
        })
    education = [{"institution": e.institution, "degree": e.degree,
                  "field": e.field or "", "start_date": e.start_date or "", "end_date": e.end_date or "Present"}
                 for e in svc.get_education_list(session)]
    projects = [{"name": p.name, "description": p.description}
                for p in svc.get_projects(session)]
    return {"skills": skills, "experiences": experiences,
            "education": education, "projects": projects}

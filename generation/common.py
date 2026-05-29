"""Shared helpers for the generation phase: prompt loading, profile JSON, language/company detection."""
import re
from functools import lru_cache
from pathlib import Path

from sqlmodel import Session

# ---------------------------------------------------------------------------
# Relevance filtering
# ---------------------------------------------------------------------------
_STOP_WORDS = frozenset([
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "will", "would", "could", "should", "may", "might",
    "this", "that", "these", "those", "we", "you", "our", "your", "their",
])

_PROMPT_DIR = Path("generation/prompts")

# Leading conversational wrappers chatty models prepend (e.g. "Here's the cover letter:")
_PREAMBLE_RE = re.compile(
    r"^\s*(here('?s| is)|sure|certainly|of course|absolutely|below is|"
    r"i('?ve| have) (written|drafted|created|prepared|revised|updated|rewritten)|"
    r"i('?d| would) be happy|i('?ve| have) revised|i('?ve| have) rewritten)"
    r"[^\n]*?(:\s*\n|\.\s*\n|\n)",
    re.IGNORECASE,
)
# Trailing offers or meta-commentary (e.g. "Let me know if you'd like any changes.")
_POSTAMBLE_RE = re.compile(
    r"\n+\s*(let me know|feel free|i hope this|hope this helps|please let me know|"
    r"i('?ve| have) (revised|updated|rewritten|removed|ensured|made sure))"
    r"[^\n]*$",
    re.IGNORECASE,
)


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Patterns that indicate a "send resume here" context — prioritised over bare emails
_EMAIL_CONTEXT_RE = re.compile(
    r"(?:kirim|send|email|apply|lamaran|cv|resume).{0,60}?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
    re.IGNORECASE,
)


def extract_contact_email(text: str) -> str | None:
    """Return the most likely HR/application email from job description text, or None."""
    if not text:
        return None
    # Prefer emails near application-context keywords
    m = _EMAIL_CONTEXT_RE.search(text)
    if m:
        return m.group(1)
    # Fall back to first email found anywhere
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else None


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


def _token_overlap(a: str, b: str) -> float:
    """Fraction of unique content words in `a` that appear in `b`."""
    a_words = {w.lower() for w in re.findall(r"\w+", a) if w.lower() not in _STOP_WORDS and len(w) > 2}
    b_lower = b.lower()
    if not a_words:
        return 0.0
    return sum(1 for w in a_words if w in b_lower) / len(a_words)


def filter_profile_for_job(profile: dict, job_description: str, top_skills: int = 10,
                           top_experiences: int = 3) -> dict:
    """Return a trimmed profile with only the most relevant skills and experiences for the job."""
    jd = job_description.lower()

    scored_skills = sorted(
        profile.get("skills", []),
        key=lambda s: _token_overlap(f"{s['name']} {s.get('keywords', '')}", jd),
        reverse=True,
    )

    def _exp_score(exp: dict) -> float:
        text = f"{exp['title']} {exp['description']} " + " ".join(
            f"{a['description']} {a.get('skills_used', '')}"
            for a in exp.get("achievements", [])
        )
        return _token_overlap(text, jd)

    scored_exps = sorted(profile.get("experiences", []), key=_exp_score, reverse=True)

    return {
        **profile,
        "skills": scored_skills[:top_skills],
        "experiences": scored_exps[:top_experiences],
    }


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

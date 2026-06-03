import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from config import settings
from db.models import Job, Skill, Experience, Preferences
from utils.logging import get_logger

log = get_logger(__name__)

# Scoring weights — must sum to 1.0
WEIGHTS = {
    "skill_match":       0.35,
    "experience_match":  0.25,
    "title_relevance":   0.20,
    "location_match":    0.10,
    "language_match":    0.05,
    "salary_match":      0.05,
}


class ParsedRequirements(BaseModel):
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    years_experience_min: Optional[float] = None
    years_experience_max: Optional[float] = None
    education_level: Optional[str] = None
    languages: list[str] = []
    experience_level: Optional[str] = None


def _parse_date(s: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt)
        except ValueError:
            continue
    return datetime.now()


def _total_experience_years(experiences: list[Experience]) -> float:
    total_months = 0
    now = datetime.now()
    for exp in experiences:
        try:
            start = _parse_date(exp.start_date)
            end = _parse_date(exp.end_date) if exp.end_date else now
            months = (end.year - start.year) * 12 + (end.month - start.month)
            total_months += max(0, months)
        except Exception:
            total_months += 12  # fallback: count as 1 year
    return total_months / 12


_JOB_PARSER_TOOL = {
    "description": "Extract structured requirements from a job posting",
    "input_schema": {
        "type": "object",
        "properties": {
            "required_skills":       {"type": "array", "items": {"type": "string"}},
            "preferred_skills":      {"type": "array", "items": {"type": "string"}},
            "years_experience_min":  {"type": "number"},
            "years_experience_max":  {"type": "number"},
            "education_level":       {"type": "string"},
            "languages":             {"type": "array", "items": {"type": "string"}},
            "experience_level":      {"type": "string", "enum": ["junior", "mid", "senior", "lead"]},
        },
        "required": ["required_skills", "preferred_skills", "languages"],
    },
}


def _parse_requirements_heuristic(description: str) -> ParsedRequirements:
    """Extract job requirements with pure regex/keyword matching — no LLM, no quota."""
    import re
    text = description.lower()

    # years of experience: "3+ years", "minimal 2 tahun", "pengalaman 5 tahun"
    years_min = None
    m = re.search(r'(\d+)\s*(?:\+|–|-|to|s/d|sd)?\s*(?:years?|tahun)\s*(?:of\s+)?(?:experience|pengalaman)', text)
    if not m:
        m = re.search(r'(?:experience|pengalaman|min(?:imal)?)[^\d]{0,20}(\d+)\s*(?:years?|tahun)', text)
    if m:
        years_min = float(m.group(1))

    # languages
    languages = []
    if any(w in text for w in ["english", "inggris", "bahasa inggris"]):
        languages.append("English")
    if any(w in text for w in ["indonesian", "indonesia", "bahasa indonesia", "bahasa"]):
        languages.append("Indonesian")

    # skills: extract capitalized/technical terms from description
    # These will be matched against user's skill list by _skill_match_direct
    skill_terms = re.findall(r'\b([A-Z][a-zA-Z0-9+#.]*(?:\s[A-Z][a-zA-Z0-9+#.]*){0,2})\b', description)
    skill_terms += re.findall(r'\b(python|java|sql|excel|sap|erp|xero|accurate|myob|zahir|odoo|quickbooks|'
                              r'ms\s*office|microsoft\s*office|powerpoint|vlookup|pivot|macro|vba|'
                              r'pajak|perpajakan|brevet|ifrs|psak|gaap|cpa|cfa|acca)\b', text)
    required_skills = list(dict.fromkeys(s.strip() for s in skill_terms if len(s.strip()) > 1))[:20]

    return ParsedRequirements(
        required_skills=required_skills,
        preferred_skills=[],
        years_experience_min=years_min,
        languages=languages,
    )


def _parse_requirements(description: str) -> ParsedRequirements:
    return _parse_requirements_heuristic(description)


def _parse_requirements_batch(jobs: list["Job"]) -> list[ParsedRequirements]:
    """Parse requirements for N jobs in a single LLM call. Falls back per-job on parse error."""
    from utils.llm import chat
    n = len(jobs)
    snippets = []
    for i, job in enumerate(jobs):
        desc = (job.description or job.title)[:800]
        snippets.append(f"JOB_{i+1} title: {job.title}\n{desc}")
    combined = "\n\n---\n\n".join(snippets)

    prompt = (
        f"Extract job requirements for each of the following {n} job postings.\n"
        f"Return a JSON array of exactly {n} objects in order, one per job.\n"
        "Each object must have these keys:\n"
        '  "required_skills": list of strings\n'
        '  "preferred_skills": list of strings\n'
        '  "years_experience_min": number or null\n'
        '  "languages": list of strings (e.g. ["English","Indonesian"])\n\n'
        f"{combined}\n\n"
        "Return ONLY the JSON array, no other text."
    )

    try:
        raw = chat(
            model=settings.scoring_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0,
        )
        start, end = raw.find("["), raw.rfind("]") + 1
        items = json.loads(raw[start:end])
        results = []
        for item in items[:n]:
            try:
                results.append(ParsedRequirements(**item))
            except Exception:
                results.append(ParsedRequirements())
        while len(results) < n:
            results.append(ParsedRequirements())
        log.debug("batch_requirements_parsed", count=n)
        return results
    except Exception as e:
        log.warning("batch_parse_failed", error=str(e))
        return [ParsedRequirements() for _ in jobs]


def _skill_match_from_text(description: str, user_skills: list[Skill]) -> float:
    """Direct keyword scan: check which user skills appear in job description text."""
    if not user_skills or not description:
        return 0.6
    text = description.lower()
    hits = 0
    for s in user_skills:
        terms = [s.name.lower()] + ([kw.strip().lower() for kw in s.keywords.split(",")] if s.keywords else [])
        if any(t and t in text for t in terms):
            hits += 1
    return min(1.0, hits / max(len(user_skills) * 0.3, 1))


def _skill_match(required: list[str], preferred: list[str], user_skills: list[Skill]) -> float:
    all_required = required + preferred
    if not all_required:
        return 0.6

    user_terms: set[str] = set()
    for s in user_skills:
        user_terms.add(s.name.lower())
        if s.keywords:
            for kw in s.keywords.split(","):
                user_terms.add(kw.strip().lower())

    # Required skills weighted double vs preferred
    req_matches = sum(1 for s in required if s.lower() in user_terms)
    pref_matches = sum(1 for s in preferred if s.lower() in user_terms)

    if required:
        req_score = req_matches / len(required)
    else:
        req_score = 0.6

    if preferred:
        pref_score = pref_matches / len(preferred)
    else:
        pref_score = 0.6

    return req_score * 0.7 + pref_score * 0.3


def _experience_match(years_min: Optional[float], user_years: float) -> float:
    if years_min is None:
        return 0.7
    if user_years >= years_min:
        return 1.0
    ratio = user_years / years_min
    if ratio >= 0.8:
        return 0.75
    if ratio >= 0.5:
        return 0.5
    return 0.25


def _location_match(job: Job, prefs: Optional[Preferences]) -> float:
    if not prefs or not prefs.target_locations:
        return 0.7
    locations = json.loads(prefs.target_locations) if isinstance(prefs.target_locations, str) else []
    locations_lower = [l.lower() for l in locations]

    if job.remote_type == "remote" and "remote" in locations_lower:
        return 1.0
    if job.remote_type == "hybrid" and "hybrid" in locations_lower:
        return 0.85
    job_loc = (job.location or "").lower()
    for loc in locations_lower:
        if loc in job_loc or job_loc in loc:
            return 0.9
    return 0.4


def title_matches_roles(title: str, roles: list[str]) -> bool:
    """True if title contains all tokens of at least one role.

    Prefix match handles plurals/gerunds (e.g. "engineer" matches "engineering").
    """
    title_tokens = set(title.lower().split())
    for role in roles:
        role_tokens = role.lower().split()
        if all(any(t.startswith(r) for t in title_tokens) for r in role_tokens):
            return True
    return False


def _title_relevance(job_title: str, prefs: Optional[Preferences]) -> float:
    if not prefs or not prefs.target_roles:
        return 0.6
    roles = json.loads(prefs.target_roles) if isinstance(prefs.target_roles, str) else []
    return 1.0 if title_matches_roles(job_title, roles) else 0.0


def _language_match(languages: list[str], prefs: Optional[Preferences]) -> float:
    if not languages:
        return 0.8
    user_langs_raw = prefs.preferred_languages if prefs else None
    user_langs = json.loads(user_langs_raw) if user_langs_raw else ["English", "Indonesian"]
    user_langs_lower = [l.lower() for l in user_langs]
    matches = sum(1 for l in languages if l.lower() in user_langs_lower)
    return min(1.0, matches / len(languages)) if languages else 0.8


def _salary_match(job: Job, prefs: Optional[Preferences]) -> float:
    if not prefs or not prefs.min_salary:
        return 0.7
    if not job.salary_min and not job.salary_max:
        return 0.6  # unknown salary — neutral
    cap = job.salary_max or job.salary_min
    floor = job.salary_min or 0
    if cap >= prefs.min_salary:
        return 1.0
    if floor >= prefs.min_salary * 0.8:
        return 0.7
    return 0.3


def score_job(job: Job, session: Session) -> tuple[float, dict]:
    """Score a job against the user profile. Returns (overall_score, breakdown_dict)."""
    skills = list(session.exec(select(Skill)).all())
    experiences = list(session.exec(select(Experience)).all())
    prefs = session.get(Preferences, 1)

    description = job.description or job.title
    requirements = _parse_requirements(description)
    user_years = _total_experience_years(experiences)

    breakdown = {
        "skill_match":       _skill_match_from_text(job.description or job.title, skills),
        "experience_match":  _experience_match(requirements.years_experience_min, user_years),
        "title_relevance":   _title_relevance(job.title, prefs),
        "location_match":    _location_match(job, prefs),
        "language_match":    _language_match(requirements.languages, prefs),
        "salary_match":      _salary_match(job, prefs),
    }

    overall = round(sum(score * WEIGHTS[key] for key, score in breakdown.items()), 3)
    log.info("job_scored", job_id=job.id, title=job.title, score=overall)
    return overall, breakdown


def score_jobs_batch(jobs: list[Job], session: Session) -> list[tuple[float, dict]]:
    """Score multiple jobs — pure heuristic, zero LLM calls."""
    skills = list(session.exec(select(Skill)).all())
    experiences = list(session.exec(select(Experience)).all())
    prefs = session.get(Preferences, 1)
    user_years = _total_experience_years(experiences)

    results = []
    for job in jobs:
        description = job.description or job.title
        requirements = _parse_requirements_heuristic(description)
        breakdown = {
            "skill_match":       _skill_match_from_text(description, skills),
            "experience_match":  _experience_match(requirements.years_experience_min, user_years),
            "title_relevance":   _title_relevance(job.title, prefs),
            "location_match":    _location_match(job, prefs),
            "language_match":    _language_match(requirements.languages, prefs),
            "salary_match":      _salary_match(job, prefs),
        }
        overall = round(sum(score * WEIGHTS[key] for key, score in breakdown.items()), 3)
        log.info("job_scored", job_id=job.id, title=job.title, score=overall)
        results.append((overall, breakdown))
    return results

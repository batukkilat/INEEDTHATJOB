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


def _parse_requirements(description: str) -> ParsedRequirements:
    from utils.llm import get_client
    client = get_client()
    prompt_tmpl = Path("generation/prompts/job_parser.txt").read_text()
    prompt = prompt_tmpl.replace("{job_description}", description[:4000])

    try:
        response = client.beta.chat.completions.parse(
            model=settings.scoring_model,
            messages=[{"role": "user", "content": prompt}],
            response_format=ParsedRequirements,
            temperature=0,
        )
        result = response.choices[0].message.parsed
        log.debug("requirements_parsed", skills=len(result.required_skills))
        return result
    except Exception as e:
        log.warning("requirements_parse_failed", error=str(e))
        return ParsedRequirements()


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


def _title_relevance(job_title: str, prefs: Optional[Preferences]) -> float:
    if not prefs or not prefs.target_roles:
        return 0.6
    roles = json.loads(prefs.target_roles) if isinstance(prefs.target_roles, str) else []
    title_lower = job_title.lower()
    for role in roles:
        words = role.lower().split()
        if sum(1 for w in words if w in title_lower) / max(len(words), 1) >= 0.5:
            return 1.0
    return 0.4


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
        "skill_match":       _skill_match(requirements.required_skills, requirements.preferred_skills, skills),
        "experience_match":  _experience_match(requirements.years_experience_min, user_years),
        "title_relevance":   _title_relevance(job.title, prefs),
        "location_match":    _location_match(job, prefs),
        "language_match":    _language_match(requirements.languages, prefs),
        "salary_match":      _salary_match(job, prefs),
    }

    overall = round(sum(score * WEIGHTS[key] for key, score in breakdown.items()), 3)
    log.info("job_scored", job_id=job.id, title=job.title, score=overall)
    return overall, breakdown

from pydantic import BaseModel
from typing import Optional


class JobRequirements(BaseModel):
    """Parsed from job description by LLM (Phase 2)."""
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    years_experience_min: Optional[float] = None
    years_experience_max: Optional[float] = None
    education_level: Optional[str] = None
    languages: list[str] = []
    experience_level: Optional[str] = None  # 'junior', 'mid', 'senior', 'lead'


class ScoringResult(BaseModel):
    """Output of the compatibility scorer (Phase 2)."""
    overall: float                 # 0.0 to 1.0
    skill_match: float
    experience_match: float
    location_match: float
    salary_match: float
    title_relevance: float
    language_match: float
    breakdown_json: str            # serialized for storage

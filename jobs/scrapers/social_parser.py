"""LLM-based parser: unstructured social media post → structured Job fields."""
import json
from datetime import datetime, timezone

from config import settings
from db.models import Job
from utils.logging import get_logger

log = get_logger(__name__)

_SYSTEM = (
    "You extract job vacancy information from social media posts (Indonesian or English). "
    "Return JSON only, no prose."
)

_PROMPT = """\
Post text:
\"\"\"
{text}
\"\"\"

Extract job vacancy details. Return a JSON object with these fields:
- "is_job_post": true/false (is this actually a job opening, not unrelated content?)
- "title": job title / role (string or null)
- "company": company or organization name (string or null)
- "location": city or "Remote" or "Indonesia" (string or null)
- "remote_type": "remote", "hybrid", "onsite", or null
- "salary_min": monthly IDR minimum salary as integer, or null
- "salary_max": monthly IDR maximum salary as integer, or null
- "description": cleaned job summary in 2-3 sentences (string or null)
- "contact": contact info (email, DM, WhatsApp number) mentioned, or null

Rules:
- If this is not a job vacancy post, return {{"is_job_post": false}} only
- Never invent data not present in the post
- Salary: convert if given as "5-8 juta" → min=5000000, max=8000000
"""


def parse_post_to_job(post_text: str, post_url: str, post_id: str,
                      platform: str, scraped_at: str | None = None) -> Job | None:
    """Use LLM to parse a social post into a Job object. Returns None if not a job post."""
    from utils.llm import chat, extract_json

    if not post_text or len(post_text.strip()) < 20:
        return None

    try:
        raw = chat(
            model=settings.scoring_model,
            messages=[{"role": "user", "content": _PROMPT.format(text=post_text[:1500])}],
            system=_SYSTEM,
            max_tokens=400,
            temperature=0,
        )
        data = extract_json(raw)
        if not data or not data.get("is_job_post"):
            return None

        title = data.get("title") or ""
        if not title:
            return None

        return Job(
            platform=platform,
            external_id=post_id,
            url=post_url,
            title=title,
            company=data.get("company") or "Unknown",
            location=data.get("location") or "Indonesia",
            remote_type=data.get("remote_type"),
            salary_min=_to_float(data.get("salary_min")),
            salary_max=_to_float(data.get("salary_max")),
            description=_build_description(post_text, data),
            posted_date=None,
            scraped_at=scraped_at or datetime.now(timezone.utc).isoformat(),
            status="new",
        )
    except Exception as e:
        log.debug("social_parse_failed", platform=platform, post_id=post_id, error=str(e))
        return None


def _to_float(val) -> float | None:
    try:
        return float(val) if val else None
    except (TypeError, ValueError):
        return None


def _build_description(post_text: str, data: dict) -> str:
    parts = []
    if data.get("description"):
        parts.append(data["description"])
    if data.get("contact"):
        parts.append(f"Contact: {data['contact']}")
    parts.append(f"\n---\nOriginal post:\n{post_text[:800]}")
    return "\n".join(parts)

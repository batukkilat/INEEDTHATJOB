"""Phase 3: application email drafting."""
import json
from pathlib import Path

from sqlmodel import Session

from config import settings
from utils.llm import chat
from utils.logging import get_logger

log = get_logger(__name__)


async def compose_email(job, session: Session) -> tuple[str, str]:
    from generation.cover_letter import _detect_language
    from generation.resume import _build_profile_json
    prompt_tmpl = Path("generation/prompts/email_draft.txt").read_text()
    language = _detect_language(job.description or job.title)

    from_name = settings.from_name or ""
    if not from_name:
        log.warning("from_name_missing", hint="Set FROM_NAME in .env — emails will lack a real name")

    profile = _build_profile_json(session)
    recent_role = ""
    if profile.get("experiences"):
        exp = profile["experiences"][0]
        recent_role = f"{exp['title']} at {exp['company']}"
    top_skills = ", ".join(s["name"] for s in profile.get("skills", [])[:6])

    prompt = (prompt_tmpl
              .replace("{job_title}", job.title)
              .replace("{company}", job.company)
              .replace("{from_name}", from_name)
              .replace("{language}", language)
              .replace("{recent_role}", recent_role)
              .replace("{top_skills}", top_skills))

    log.info("email_compose_start", job_id=job.id)
    text = chat(
        model=settings.scoring_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )

    subject = f"Application – {job.title}"
    body = text
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            data = json.loads(text[start:end])
            subject = data.get("subject", subject)
            body = data.get("body", text)
    except (json.JSONDecodeError, ValueError):
        pass

    log.info("email_compose_done", job_id=job.id)
    return subject, body

"""Phase 3: application email drafting."""
from sqlmodel import Session

from config import settings
from generation.common import build_profile_json, detect_language, load_prompt
from utils.llm import chat, extract_json
from utils.logging import get_logger

log = get_logger(__name__)


async def compose_email(job, session: Session, profile: dict | None = None) -> tuple[str, str]:
    prompt_tmpl = load_prompt("email_draft.txt")
    if profile is None:
        profile = build_profile_json(session)
    language = detect_language(job.description or job.title)

    from_name = settings.from_name or ""
    if not from_name:
        log.warning("from_name_missing", hint="Set FROM_NAME in .env — emails will lack a real name")

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
    data = extract_json(text)
    if data:
        subject = data.get("subject", subject)
        body = data.get("body", text)

    log.info("email_compose_done", job_id=job.id)
    return subject, body

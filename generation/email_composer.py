"""Phase 3: application email drafting."""
import asyncio

from sqlmodel import Session

from config import settings
from generation.common import (
    build_profile_json, detect_language, filter_profile_for_job,
    load_prompt, strip_preamble,
)
from utils.llm import chat, extract_json
from utils.logging import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are a professional job applicant writing a concise, human application email. "
    "You write like a real person — direct, specific, no corporate-speak. "
    "You always return valid JSON with exactly two fields: subject and body."
)


async def compose_email(job, session: Session, profile: dict | None = None) -> tuple[str, str]:
    prompt_tmpl = load_prompt("email_draft.txt")
    if profile is None:
        profile = build_profile_json(session)

    jd = job.description or job.title
    filtered = filter_profile_for_job(profile, jd, top_skills=6, top_experiences=2)

    language = detect_language(jd)
    from_name = settings.from_name or ""
    if not from_name:
        log.warning("from_name_missing", hint="Set FROM_NAME in .env — emails will lack a real name")
        from_name = "[Your Name]"

    recent_role = ""
    if filtered.get("experiences"):
        exp = filtered["experiences"][0]
        recent_role = f"{exp['title']} at {exp['company']}"
    top_skills = ", ".join(s["name"] for s in filtered.get("skills", [])[:6])

    user_prompt = (prompt_tmpl
                   .replace("{job_title}", job.title)
                   .replace("{company}", job.company)
                   .replace("{from_name}", from_name)
                   .replace("{language}", language)
                   .replace("{recent_role}", recent_role)
                   .replace("{top_skills}", top_skills))

    log.info("email_compose_start", job_id=job.id)
    text = await asyncio.to_thread(
        chat,
        model=settings.generation_model,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=512,
        temperature=0.3,
    )

    subject = f"Application – {job.title}"
    body = strip_preamble(text)
    data = extract_json(text)
    if data:
        subject = data.get("subject", subject)
        body = strip_preamble(data.get("body", body))

    log.info("email_compose_done", job_id=job.id)
    return subject, body

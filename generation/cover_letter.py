"""Phase 3: cover letter generation (English + Indonesian)."""
import json

from sqlmodel import Session

from config import settings
from generation.common import build_profile_json, company_type, detect_language, load_prompt
from utils.llm import chat
from utils.logging import get_logger

log = get_logger(__name__)


async def generate_cover_letter(job, session: Session, profile: dict | None = None) -> str:
    prompt_tmpl = load_prompt("cover_letter.txt")
    if profile is None:
        profile = build_profile_json(session)
    language = detect_language(job.description or job.title)

    from_name = settings.from_name or ""
    if not from_name:
        log.warning("from_name_missing", hint="Set FROM_NAME in .env — cover letter will lack a real name")

    prompt = (prompt_tmpl
              .replace("{job_title}", job.title)
              .replace("{company}", job.company)
              .replace("{job_description}", (job.description or job.title)[:2500])
              .replace("{profile_json}", json.dumps(profile, ensure_ascii=False)[:2500])
              .replace("{language}", language)
              .replace("{company_type}", company_type(job.company))
              .replace("{from_name}", from_name))

    log.info("cover_letter_start", job_id=job.id, language=language)
    result = chat(
        model=settings.generation_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    log.info("cover_letter_done", job_id=job.id)
    return result.strip()

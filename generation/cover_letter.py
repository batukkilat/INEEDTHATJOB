"""Phase 3: cover letter generation (English + Indonesian)."""
import json
from pathlib import Path

from sqlmodel import Session

from config import settings
from utils.llm import chat
from utils.logging import get_logger

log = get_logger(__name__)


def _detect_language(text: str) -> str:
    indonesian_markers = ["kami", "anda", "untuk", "dengan", "dalam", "adalah",
                          "yang", "di ", "dan ", "atau ", "dari ", "pada "]
    text_lower = text.lower()
    hits = sum(1 for m in indonesian_markers if m in text_lower)
    return "Indonesian" if hits >= 3 else "English"


def _company_type(company: str) -> str:
    company_lower = company.lower()
    if any(w in company_lower for w in ["startup", "tech", "labs", "studio"]):
        return "startup"
    if any(w in company_lower for w in ["bank", "finance", "tbk", "pt."]):
        return "corporate"
    return "professional"


async def generate_cover_letter(job, session: Session) -> str:
    import profile.service as svc
    from generation.resume import _build_profile_json

    prompt_tmpl = Path("generation/prompts/cover_letter.txt").read_text()
    profile = _build_profile_json(session)
    language = _detect_language(job.description or job.title)

    from_name = settings.from_name or ""
    if not from_name:
        log.warning("from_name_missing", hint="Set FROM_NAME in .env — cover letter will lack a real name")

    prompt = (prompt_tmpl
              .replace("{job_title}", job.title)
              .replace("{company}", job.company)
              .replace("{job_description}", (job.description or job.title)[:2500])
              .replace("{profile_json}", json.dumps(profile, ensure_ascii=False)[:2500])
              .replace("{language}", language)
              .replace("{company_type}", _company_type(job.company))
              .replace("{from_name}", from_name))

    log.info("cover_letter_start", job_id=job.id, language=language)
    result = chat(
        model=settings.generation_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    log.info("cover_letter_done", job_id=job.id)
    return result.strip()

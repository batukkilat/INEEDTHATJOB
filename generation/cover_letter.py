"""Phase 3: cover letter generation (English + Indonesian)."""
import asyncio
import json
import re

from sqlmodel import Session

from config import settings
from generation.common import (
    build_profile_json, company_type, detect_language,
    filter_profile_for_job, load_prompt, strip_preamble,
)
from utils.llm import chat
from utils.logging import get_logger

log = get_logger(__name__)

# Percentages and multi-digit quantities are the figures models most often fabricate.
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%|\b\d{2,}\b")

_SYSTEM_PROMPT = (
    "You are an expert career coach and professional writer specialising in the Indonesian job market. "
    "You write cover letters that sound like a real, confident professional — not a template. "
    "You follow instructions precisely and never invent facts, metrics, or experience."
)

_CRITIQUE_PROMPT = (
    "\n\nReview your draft. Fix any paragraph that could appear in any other cover letter — make it "
    "specific to this role and company. Fix any banned phrase that slipped through.\n"
    "Output ONLY the revised letter text. No explanation, no commentary, no preamble about what you changed. "
    "Start directly with the first word of the letter."
)


def _fabricated_numbers(text: str, profile_text: str) -> list[str]:
    """Return numeric figures in the letter that do not appear in the profile data."""
    bad = []
    for fig in _NUMBER_RE.findall(text):
        norm = fig.rstrip("%").replace(",", "")
        if fig not in profile_text and norm not in profile_text:
            bad.append(fig)
    return bad


async def generate_cover_letter(job, session: Session, profile: dict | None = None) -> str:
    prompt_tmpl = load_prompt("cover_letter.txt")
    if profile is None:
        profile = build_profile_json(session)

    jd = job.description or job.title
    filtered = filter_profile_for_job(profile, jd)
    profile_text = json.dumps(filtered, ensure_ascii=False)

    language = detect_language(jd)
    from_name = settings.from_name or ""
    if not from_name:
        log.warning("from_name_missing", hint="Set FROM_NAME in .env — cover letter will lack a real name")

    user_prompt = (prompt_tmpl
                   .replace("{job_title}", job.title)
                   .replace("{company}", job.company)
                   .replace("{job_description}", jd[:2500])
                   .replace("{profile_json}", profile_text[:3000])
                   .replace("{language}", language)
                   .replace("{company_type}", company_type(job.company))
                   .replace("{from_name}", from_name))

    log.info("cover_letter_start", job_id=job.id, language=language)

    fabricated: list[str] = []
    letter = ""
    for attempt in range(2):
        if attempt == 0:
            messages = [{"role": "user", "content": user_prompt}]
        else:
            # Pass 1: fabricated numbers found — name them and ask for rewrite
            messages = [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": letter},
                {"role": "user", "content": (
                    f"Your draft includes these figures that are NOT in the profile: "
                    f"{', '.join(fabricated)}. Rewrite without any invented numbers — "
                    f"describe those achievements qualitatively instead. Output only the letter."
                )},
            ]

        result = await asyncio.to_thread(
            chat,
            model=settings.generation_model,
            system=_SYSTEM_PROMPT,
            messages=messages,
            max_tokens=1024,
            temperature=0.3,
        )
        letter = strip_preamble(result)
        fabricated = _fabricated_numbers(letter, profile_text)
        if not fabricated:
            break
        log.warning("cover_letter_fabricated_numbers", job_id=job.id, figures=fabricated, attempt=attempt + 1)

    # Critique-and-revise pass: ask the model to self-check specificity
    critique_result = await asyncio.to_thread(
        chat,
        model=settings.generation_model,
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": letter},
            {"role": "user", "content": _CRITIQUE_PROMPT},
        ],
        max_tokens=1024,
        temperature=0.2,
    )
    revised = strip_preamble(critique_result)
    # Only accept the revision if it didn't introduce new fabricated numbers
    if not _fabricated_numbers(revised, profile_text):
        letter = revised

    log.info("cover_letter_done", job_id=job.id)
    return letter

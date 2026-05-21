import io
from pathlib import Path

from sqlmodel import Session, select

from db.models import Skill, Experience, Achievement, Education, Certification, Project
from profile.resume_parser import parse_resume_text
from utils.logging import get_logger

log = get_logger(__name__)

_RESUME_PARSER_TOOL = {
    "description": "Extract all professional profile data from a resume",
    "input_schema": {
        "type": "object",
        "properties": {
            "skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":             {"type": "string"},
                        "category":         {"type": "string", "enum": ["technical", "soft", "domain", "language"]},
                        "proficiency":      {"type": "string", "enum": ["expert", "advanced", "intermediate", "beginner"]},
                        "years_experience": {"type": "number"},
                        "keywords":         {"type": "string"},
                    },
                    "required": ["name", "category"],
                },
            },
            "experiences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company":     {"type": "string"},
                        "title":       {"type": "string"},
                        "start_date":  {"type": "string"},
                        "end_date":    {"type": "string"},
                        "location":    {"type": "string"},
                        "description": {"type": "string"},
                        "is_remote":   {"type": "boolean"},
                        "achievements": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "metrics":     {"type": "string"},
                                    "skills_used": {"type": "string"},
                                },
                                "required": ["description"],
                            },
                        },
                    },
                    "required": ["company", "title", "start_date"],
                },
            },
            "education": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "institution": {"type": "string"},
                        "degree":      {"type": "string"},
                        "field":       {"type": "string"},
                        "start_date":  {"type": "string"},
                        "end_date":    {"type": "string"},
                        "gpa":         {"type": "string"},
                    },
                    "required": ["institution", "degree"],
                },
            },
            "certifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":           {"type": "string"},
                        "issuer":         {"type": "string"},
                        "date_obtained":  {"type": "string"},
                        "expiry_date":    {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            "projects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":        {"type": "string"},
                        "description": {"type": "string"},
                        "url":         {"type": "string"},
                        "skills_used": {"type": "string"},
                        "highlights":  {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        },
        "required": ["skills", "experiences", "education"],
    },
}


def extract_text(content: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return _extract_pdf(content)
    if name.endswith(".docx"):
        return _extract_docx(content)
    raise ValueError(f"Unsupported file type: {filename}. Upload a PDF or DOCX.")


def _extract_pdf(content: bytes) -> str:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    text = "\n\n".join(p for p in pages if p.strip())
    if not text.strip():
        raise ValueError("Could not extract text from this PDF. It may be image-based — try a DOCX version.")
    return text


def _extract_docx(content: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(content))
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(lines)
    if not text.strip():
        raise ValueError("Could not extract text from this DOCX file.")
    return text


def parse_resume(text: str) -> dict:
    log.info("resume_parse_start", chars=len(text))
    result = parse_resume_text(text)
    log.info("resume_parse_done",
             skills=len(result.get("skills", [])),
             experiences=len(result.get("experiences", [])))
    return result


def save_to_profile(session: Session, parsed: dict) -> dict:
    """Write parsed resume data into the DB. Skips duplicates by name/company+title."""
    counts = {"skills": 0, "experiences": 0, "education": 0, "certifications": 0, "projects": 0}

    # Skills — skip if name already exists
    existing_skill_names = {s.name.lower() for s in session.exec(select(Skill)).all()}
    for s in parsed.get("skills", []):
        if not s.get("name"):
            continue
        if s["name"].lower() in existing_skill_names:
            continue
        session.add(Skill(
            name=s["name"],
            category=s.get("category"),
            proficiency=s.get("proficiency"),
            years_experience=s.get("years_experience"),
            keywords=s.get("keywords"),
        ))
        existing_skill_names.add(s["name"].lower())
        counts["skills"] += 1

    # Experiences — skip if same company + title already exists
    existing_exp = {
        (e.company.lower(), e.title.lower())
        for e in session.exec(select(Experience)).all()
    }
    for e in parsed.get("experiences", []):
        if not e.get("company") or not e.get("title"):
            continue
        key = (e["company"].lower(), e["title"].lower())
        if key in existing_exp:
            continue
        exp = Experience(
            company=e["company"],
            title=e["title"],
            start_date=e["start_date"],
            end_date=e.get("end_date"),
            location=e.get("location"),
            description=e.get("description"),
            is_remote=bool(e.get("is_remote", False)),
        )
        session.add(exp)
        session.flush()  # get exp.id
        for a in e.get("achievements", []):
            if not a.get("description"):
                continue
            session.add(Achievement(
                experience_id=exp.id,
                description=a["description"],
                metrics=a.get("metrics"),
                skills_used=a.get("skills_used"),
            ))
        existing_exp.add(key)
        counts["experiences"] += 1

    # Education
    existing_edu = {
        (ed.institution.lower(), ed.degree.lower())
        for ed in session.exec(select(Education)).all()
    }
    for ed in parsed.get("education", []):
        if not ed.get("institution") or not ed.get("degree"):
            continue
        key = (ed["institution"].lower(), ed["degree"].lower())
        if key in existing_edu:
            continue
        session.add(Education(
            institution=ed["institution"],
            degree=ed["degree"],
            field=ed.get("field"),
            start_date=ed.get("start_date"),
            end_date=ed.get("end_date"),
            gpa=ed.get("gpa"),
        ))
        existing_edu.add(key)
        counts["education"] += 1

    # Certifications
    existing_certs = {c.name.lower() for c in session.exec(select(Certification)).all()}
    for c in parsed.get("certifications", []):
        if not c.get("name") or c["name"].lower() in existing_certs:
            continue
        session.add(Certification(
            name=c["name"],
            issuer=c.get("issuer"),
            date_obtained=c.get("date_obtained"),
            expiry_date=c.get("expiry_date"),
        ))
        existing_certs.add(c["name"].lower())
        counts["certifications"] += 1

    # Projects
    existing_projects = {p.name.lower() for p in session.exec(select(Project)).all()}
    for p in parsed.get("projects", []):
        if not p.get("name") or p["name"].lower() in existing_projects:
            continue
        session.add(Project(
            name=p["name"],
            description=p.get("description"),
            url=p.get("url"),
            skills_used=p.get("skills_used"),
            highlights=p.get("highlights"),
        ))
        existing_projects.add(p["name"].lower())
        counts["projects"] += 1

    session.commit()
    return counts

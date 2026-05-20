from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from web.templates_env import templates
from sqlmodel import Session
from db.database import get_session
from db.models import Skill, Experience, Achievement, Education, Certification, Project
import profile.service as svc

router = APIRouter()


T = "web/templates"


def _r(request, template, ctx):
    return templates.TemplateResponse(request, template, ctx)


# ── Profile page ─────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def profile_page(request: Request, session: Session = Depends(get_session)):
    return _r(request, "profile/editor.html", {
        "current_page": "profile",
        "skills": svc.get_skills(session),
        "experiences": svc.get_experiences(session),
        "education": svc.get_education_list(session),
        "certifications": svc.get_certifications(session),
        "projects": svc.get_projects(session),
    })


# ── Skills ───────────────────────────────────────────────────────────────────

@router.get("/skills/new", response_class=HTMLResponse)
def skill_new_form(request: Request):
    return _r(request, "partials/skill_add_form.html", {})


@router.post("/skills", response_class=HTMLResponse)
def skill_create(
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    category: str = Form(""),
    proficiency: str = Form(""),
    years_experience: str = Form(""),
    keywords: str = Form(""),
):
    skill = svc.create_skill(session, {
        "name": name,
        "category": category or None,
        "proficiency": proficiency or None,
        "years_experience": float(years_experience) if years_experience.strip() else None,
        "keywords": keywords or None,
    })
    return templates.TemplateResponse(request, "partials/skill_row.html", {
        "skill": skill,
        "oob_clear_skill_form": True,
    })


@router.get("/skills/{skill_id}/edit", response_class=HTMLResponse)
def skill_edit_form(skill_id: int, request: Request, session: Session = Depends(get_session)):
    skill = session.get(Skill, skill_id)
    return _r(request, "partials/skill_form_row.html", {"skill": skill})


@router.get("/skills/{skill_id}/row", response_class=HTMLResponse)
def skill_row(skill_id: int, request: Request, session: Session = Depends(get_session)):
    skill = session.get(Skill, skill_id)
    return _r(request, "partials/skill_row.html", {"skill": skill})


@router.put("/skills/{skill_id}", response_class=HTMLResponse)
def skill_update(
    skill_id: int,
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    category: str = Form(""),
    proficiency: str = Form(""),
    years_experience: str = Form(""),
    keywords: str = Form(""),
):
    skill = svc.update_skill(session, skill_id, {
        "name": name,
        "category": category or None,
        "proficiency": proficiency or None,
        "years_experience": float(years_experience) if years_experience.strip() else None,
        "keywords": keywords or None,
    })
    return _r(request, "partials/skill_row.html", {"skill": skill})


@router.delete("/skills/{skill_id}", response_class=HTMLResponse)
def skill_delete(skill_id: int, session: Session = Depends(get_session)):
    svc.delete_skill(session, skill_id)
    return HTMLResponse("")


# ── Experiences ───────────────────────────────────────────────────────────────

@router.get("/experiences/new", response_class=HTMLResponse)
def experience_new_form(request: Request):
    return _r(request, "partials/experience_form.html", {"experience": None})


@router.post("/experiences", response_class=HTMLResponse)
def experience_create(
    request: Request,
    session: Session = Depends(get_session),
    company: str = Form(...),
    title: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(""),
    location: str = Form(""),
    description: str = Form(""),
    is_remote: str = Form(""),
):
    exp = svc.create_experience(session, {
        "company": company,
        "title": title,
        "start_date": start_date,
        "end_date": end_date or None,
        "location": location or None,
        "description": description or None,
        "is_remote": bool(is_remote),
    })
    return templates.TemplateResponse(request, "partials/experience_card.html", {
        "experience": exp,
        "oob_clear_experience_form": True,
    })


@router.get("/experiences/{exp_id}/edit", response_class=HTMLResponse)
def experience_edit_form(exp_id: int, request: Request, session: Session = Depends(get_session)):
    exp = session.get(Experience, exp_id)
    return _r(request, "partials/experience_form.html", {"experience": exp})


@router.get("/experiences/{exp_id}/card", response_class=HTMLResponse)
def experience_card(exp_id: int, request: Request, session: Session = Depends(get_session)):
    exp = session.get(Experience, exp_id)
    return _r(request, "partials/experience_card.html", {"experience": exp})


@router.put("/experiences/{exp_id}", response_class=HTMLResponse)
def experience_update(
    exp_id: int,
    request: Request,
    session: Session = Depends(get_session),
    company: str = Form(...),
    title: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(""),
    location: str = Form(""),
    description: str = Form(""),
    is_remote: str = Form(""),
):
    exp = svc.update_experience(session, exp_id, {
        "company": company,
        "title": title,
        "start_date": start_date,
        "end_date": end_date or None,
        "location": location or None,
        "description": description or None,
        "is_remote": bool(is_remote),
    })
    return _r(request, "partials/experience_card.html", {"experience": exp})


@router.delete("/experiences/{exp_id}", response_class=HTMLResponse)
def experience_delete(exp_id: int, session: Session = Depends(get_session)):
    svc.delete_experience(session, exp_id)
    return HTMLResponse("")


# ── Achievements ──────────────────────────────────────────────────────────────

@router.get("/experiences/{exp_id}/achievements/new", response_class=HTMLResponse)
def achievement_new_form(exp_id: int, request: Request):
    return _r(request, "partials/achievement_form.html", {"experience_id": exp_id, "achievement": None})


@router.post("/experiences/{exp_id}/achievements", response_class=HTMLResponse)
def achievement_create(
    exp_id: int,
    request: Request,
    session: Session = Depends(get_session),
    description: str = Form(...),
    metrics: str = Form(""),
    skills_used: str = Form(""),
):
    a = svc.create_achievement(session, {
        "experience_id": exp_id,
        "description": description,
        "metrics": metrics or None,
        "skills_used": skills_used or None,
    })
    return templates.TemplateResponse(request, "partials/achievement_row.html", {
        "achievement": a, "exp_id": exp_id,
        "oob_clear_achievement_form": exp_id,
    })


@router.get("/achievements/{achievement_id}/edit", response_class=HTMLResponse)
def achievement_edit_form(achievement_id: int, request: Request, session: Session = Depends(get_session)):
    a = session.get(Achievement, achievement_id)
    return _r(request, "partials/achievement_form.html", {"experience_id": a.experience_id, "achievement": a})


@router.get("/achievements/{achievement_id}/row", response_class=HTMLResponse)
def achievement_row(achievement_id: int, request: Request, session: Session = Depends(get_session)):
    a = session.get(Achievement, achievement_id)
    return _r(request, "partials/achievement_row.html", {"achievement": a, "exp_id": a.experience_id})


@router.put("/achievements/{achievement_id}", response_class=HTMLResponse)
def achievement_update(
    achievement_id: int,
    request: Request,
    session: Session = Depends(get_session),
    description: str = Form(...),
    metrics: str = Form(""),
    skills_used: str = Form(""),
):
    a = svc.update_achievement(session, achievement_id, {
        "description": description,
        "metrics": metrics or None,
        "skills_used": skills_used or None,
    })
    return _r(request, "partials/achievement_row.html", {"achievement": a, "exp_id": a.experience_id})


@router.delete("/achievements/{achievement_id}", response_class=HTMLResponse)
def achievement_delete(achievement_id: int, session: Session = Depends(get_session)):
    svc.delete_achievement(session, achievement_id)
    return HTMLResponse("")


# ── Education ─────────────────────────────────────────────────────────────────

@router.get("/education/new", response_class=HTMLResponse)
def education_new_form(request: Request):
    return _r(request, "partials/education_form.html", {"edu": None})


@router.post("/education", response_class=HTMLResponse)
def education_create(
    request: Request,
    session: Session = Depends(get_session),
    institution: str = Form(...),
    degree: str = Form(...),
    field: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    gpa: str = Form(""),
):
    edu = svc.create_education(session, {
        "institution": institution,
        "degree": degree,
        "field": field or None,
        "start_date": start_date or None,
        "end_date": end_date or None,
        "gpa": gpa or None,
    })
    return templates.TemplateResponse(request, "partials/education_row.html", {
        "edu": edu, "oob_clear_education_form": True,
    })


@router.get("/education/{edu_id}/edit", response_class=HTMLResponse)
def education_edit_form(edu_id: int, request: Request, session: Session = Depends(get_session)):
    edu = session.get(Education, edu_id)
    return _r(request, "partials/education_form.html", {"edu": edu})


@router.get("/education/{edu_id}/row", response_class=HTMLResponse)
def education_row(edu_id: int, request: Request, session: Session = Depends(get_session)):
    edu = session.get(Education, edu_id)
    return _r(request, "partials/education_row.html", {"edu": edu})


@router.put("/education/{edu_id}", response_class=HTMLResponse)
def education_update(
    edu_id: int,
    request: Request,
    session: Session = Depends(get_session),
    institution: str = Form(...),
    degree: str = Form(...),
    field: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    gpa: str = Form(""),
):
    edu = svc.update_education(session, edu_id, {
        "institution": institution,
        "degree": degree,
        "field": field or None,
        "start_date": start_date or None,
        "end_date": end_date or None,
        "gpa": gpa or None,
    })
    return _r(request, "partials/education_row.html", {"edu": edu})


@router.delete("/education/{edu_id}", response_class=HTMLResponse)
def education_delete(edu_id: int, session: Session = Depends(get_session)):
    svc.delete_education(session, edu_id)
    return HTMLResponse("")


# ── Certifications ────────────────────────────────────────────────────────────

@router.get("/certifications/new", response_class=HTMLResponse)
def certification_new_form(request: Request):
    return _r(request, "partials/certification_form.html", {"cert": None})


@router.post("/certifications", response_class=HTMLResponse)
def certification_create(
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    issuer: str = Form(""),
    date_obtained: str = Form(""),
    expiry_date: str = Form(""),
):
    cert = svc.create_certification(session, {
        "name": name,
        "issuer": issuer or None,
        "date_obtained": date_obtained or None,
        "expiry_date": expiry_date or None,
    })
    return templates.TemplateResponse(request, "partials/certification_row.html", {
        "cert": cert, "oob_clear_cert_form": True,
    })


@router.get("/certifications/{cert_id}/edit", response_class=HTMLResponse)
def certification_edit_form(cert_id: int, request: Request, session: Session = Depends(get_session)):
    cert = session.get(Certification, cert_id)
    return _r(request, "partials/certification_form.html", {"cert": cert})


@router.get("/certifications/{cert_id}/row", response_class=HTMLResponse)
def certification_row(cert_id: int, request: Request, session: Session = Depends(get_session)):
    cert = session.get(Certification, cert_id)
    return _r(request, "partials/certification_row.html", {"cert": cert})


@router.put("/certifications/{cert_id}", response_class=HTMLResponse)
def certification_update(
    cert_id: int,
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    issuer: str = Form(""),
    date_obtained: str = Form(""),
    expiry_date: str = Form(""),
):
    cert = svc.update_certification(session, cert_id, {
        "name": name,
        "issuer": issuer or None,
        "date_obtained": date_obtained or None,
        "expiry_date": expiry_date or None,
    })
    return _r(request, "partials/certification_row.html", {"cert": cert})


@router.delete("/certifications/{cert_id}", response_class=HTMLResponse)
def certification_delete(cert_id: int, session: Session = Depends(get_session)):
    svc.delete_certification(session, cert_id)
    return HTMLResponse("")


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/projects/new", response_class=HTMLResponse)
def project_new_form(request: Request):
    return _r(request, "partials/project_form.html", {"project": None})


@router.post("/projects", response_class=HTMLResponse)
def project_create(
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    description: str = Form(""),
    url: str = Form(""),
    skills_used: str = Form(""),
    highlights: str = Form(""),
):
    project = svc.create_project(session, {
        "name": name,
        "description": description or None,
        "url": url or None,
        "skills_used": skills_used or None,
        "highlights": highlights or None,
    })
    return templates.TemplateResponse(request, "partials/project_card.html", {
        "project": project, "oob_clear_project_form": True,
    })


@router.get("/projects/{project_id}/edit", response_class=HTMLResponse)
def project_edit_form(project_id: int, request: Request, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    return _r(request, "partials/project_form.html", {"project": project})


@router.get("/projects/{project_id}/card", response_class=HTMLResponse)
def project_card(project_id: int, request: Request, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    return _r(request, "partials/project_card.html", {"project": project})


@router.put("/projects/{project_id}", response_class=HTMLResponse)
def project_update(
    project_id: int,
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    description: str = Form(""),
    url: str = Form(""),
    skills_used: str = Form(""),
    highlights: str = Form(""),
):
    project = svc.update_project(session, project_id, {
        "name": name,
        "description": description or None,
        "url": url or None,
        "skills_used": skills_used or None,
        "highlights": highlights or None,
    })
    return _r(request, "partials/project_card.html", {"project": project})


@router.delete("/projects/{project_id}", response_class=HTMLResponse)
def project_delete(project_id: int, session: Session = Depends(get_session)):
    svc.delete_project(session, project_id)
    return HTMLResponse("")

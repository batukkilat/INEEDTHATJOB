from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from web.templates_env import templates
from sqlmodel import Session
from db.database import get_session
from config import settings as app_settings
import profile.service as profile_service
import scheduler as sched

router = APIRouter()


def _settings_ctx(request: Request, session: Session, **extra) -> dict:
    prefs = profile_service.get_preferences(session)
    return {
        "current_page": "settings",
        "prefs": prefs,
        "schedule_status": sched.get_status(),
        "smtp_config": {
            "host": app_settings.smtp_host,
            "port": app_settings.smtp_port,
            "user": app_settings.smtp_user,
            "from_email": app_settings.from_email,
            "from_name": app_settings.from_name,
            "configured": bool(app_settings.smtp_user and app_settings.smtp_password),
        },
        **extra,
    }


@router.get("/", response_class=HTMLResponse)
def settings_page(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "settings.html", _settings_ctx(request, session))


@router.post("/preferences", response_class=HTMLResponse)
def save_preferences(
    request: Request,
    session: Session = Depends(get_session),
    target_roles: str = Form(""),
    target_locations: str = Form(""),
    min_salary: str = Form(""),
    max_salary: str = Form(""),
    salary_currency: str = Form("IDR"),
    preferred_languages: str = Form(""),
    company_size_preference: str = Form(""),
):
    profile_service.update_preferences(session, {
        "target_roles": target_roles or None,
        "target_locations": target_locations or None,
        "min_salary": float(min_salary) if min_salary.strip() else None,
        "max_salary": float(max_salary) if max_salary.strip() else None,
        "salary_currency": salary_currency,
        "preferred_languages": preferred_languages or None,
        "company_size_preference": company_size_preference or None,
    })
    return templates.TemplateResponse(request, "settings.html",
                                      _settings_ctx(request, session, saved=True))


@router.post("/schedule/toggle", response_class=HTMLResponse)
def toggle_schedule(request: Request, session: Session = Depends(get_session)):
    current = sched.get_status()["enabled"]
    sched.set_enabled(not current)
    return templates.TemplateResponse(request, "partials/schedule_card.html",
                                      {"schedule_status": sched.get_status()})


@router.post("/schedule/cron", response_class=HTMLResponse)
def update_cron(
    request: Request,
    cron: str = Form(...),
    session: Session = Depends(get_session),
):
    cron = cron.strip()
    if cron:
        sched.set_cron(cron)
    return templates.TemplateResponse(request, "partials/schedule_card.html",
                                      {"schedule_status": sched.get_status()})

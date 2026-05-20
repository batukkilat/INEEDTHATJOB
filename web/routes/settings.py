from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from web.templates_env import templates
from sqlmodel import Session
from db.database import get_session
import profile.service as profile_service

router = APIRouter()



@router.get("/", response_class=HTMLResponse)
def settings_page(request: Request, session: Session = Depends(get_session)):
    prefs = profile_service.get_preferences(session)
    return templates.TemplateResponse(request, "settings.html", {
        "current_page": "settings",
        "prefs": prefs,
    })


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
    prefs = profile_service.get_preferences(session)
    return templates.TemplateResponse(request, "settings.html", {
        "current_page": "settings",
        "prefs": prefs,
        "saved": True,
    })

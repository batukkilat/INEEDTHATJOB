from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from web.templates_env import templates
from sqlmodel import Session
from db.database import get_session
from config import settings as app_settings
import profile.service as profile_service
import scheduler as sched
from utils.logging import get_logger

log = get_logger(__name__)

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


def _update_env_file(updates: dict[str, str]) -> None:
    """Atomically update key=value pairs in .env. Uses os.replace() so a crash mid-write never corrupts the file."""
    import os, tempfile
    from pathlib import Path
    env_path = Path(__file__).resolve().parents[2] / ".env"
    try:
        text = env_path.read_text() if env_path.exists() else ""
    except Exception:
        text = ""
    lines = text.splitlines(keepends=True)
    touched: set[str] = set()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            result.append(line)
            continue
        key = stripped.split("=", 1)[0].strip().upper()
        if key in updates:
            result.append(f"{key}={updates[key]}\n")
            touched.add(key)
        else:
            result.append(line)
    for key, val in updates.items():
        if key not in touched:
            result.append(f"{key}={val}\n")
    # Write to temp then atomically replace
    fd, tmp = tempfile.mkstemp(dir=env_path.parent, prefix=".env.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.writelines(result)
        os.replace(tmp, str(env_path))
    except Exception:
        with __import__("contextlib").suppress(OSError):
            os.unlink(tmp)
        raise


@router.post("/smtp/save", response_class=HTMLResponse)
async def smtp_save(
    request: Request,
    session: Session = Depends(get_session),
    smtp_host: str = Form("smtp.gmail.com"),
    smtp_port: str = Form("587"),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    from_email: str = Form(""),
    from_name: str = Form(""),
):
    port = int(smtp_port.strip()) if smtp_port.strip().isdigit() else 587
    updates = {
        "SMTP_HOST": smtp_host.strip(),
        "SMTP_PORT": str(port),
        "SMTP_USER": smtp_user.strip(),
        "FROM_EMAIL": from_email.strip(),
        "FROM_NAME": from_name.strip(),
    }
    if smtp_password.strip():
        updates["SMTP_PASSWORD"] = smtp_password.strip()
    _update_env_file(updates)
    app_settings.smtp_host = updates["SMTP_HOST"]
    app_settings.smtp_port = port
    app_settings.smtp_user = updates["SMTP_USER"]
    app_settings.from_email = updates["FROM_EMAIL"]
    app_settings.from_name = updates["FROM_NAME"]
    if smtp_password.strip():
        app_settings.smtp_password = smtp_password.strip()
    log.info("smtp_config_updated", user=updates["SMTP_USER"])
    return templates.TemplateResponse(request, "settings.html",
                                      _settings_ctx(request, session, smtp_saved=True))


@router.post("/smtp/test", response_class=HTMLResponse)
async def smtp_test(to: str = Form(...)):
    import smtplib, ssl
    from email.message import EmailMessage

    to = to.strip()
    if not to:
        return HTMLResponse('<span class="text-red-500 text-sm">Enter a recipient email.</span>')
    if not (app_settings.smtp_user and app_settings.smtp_password):
        return HTMLResponse('<span class="text-red-500 text-sm">SMTP not configured — save credentials above first.</span>')

    try:
        msg = EmailMessage()
        msg["Subject"] = "INEEDTHATJOB — SMTP test"
        msg["From"] = f"{app_settings.from_name or ''} <{app_settings.from_email or app_settings.smtp_user}>"
        msg["To"] = to
        msg.set_content("SMTP is working. You can send job applications from INEEDTHATJOB.")

        ctx = ssl.create_default_context()
        with smtplib.SMTP(app_settings.smtp_host, app_settings.smtp_port) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.login(app_settings.smtp_user, app_settings.smtp_password)
            smtp.send_message(msg)

        log.info("smtp_test_sent", to=to)
        return HTMLResponse(f'<span class="text-green-600 text-sm font-medium">✓ Test email sent to {to}</span>')
    except Exception as e:
        log.error("smtp_test_failed", error=str(e))
        return HTMLResponse(f'<span class="text-red-500 text-sm">Failed: {e}</span>')


@router.post("/schedule/toggle", response_class=HTMLResponse)
async def toggle_schedule(request: Request, session: Session = Depends(get_session)):
    current = sched.get_status()["enabled"]
    sched.set_enabled(not current)
    return templates.TemplateResponse(request, "partials/schedule_card.html",
                                      {"schedule_status": sched.get_status()})


@router.post("/schedule/cron", response_class=HTMLResponse)
async def update_cron(
    request: Request,
    cron: str = Form(...),
    session: Session = Depends(get_session),
):
    cron = cron.strip()
    if cron:
        sched.set_cron(cron)
    return templates.TemplateResponse(request, "partials/schedule_card.html",
                                      {"schedule_status": sched.get_status()})

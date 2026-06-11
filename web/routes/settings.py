import asyncio
import time

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
        "cookies_config": {
            "linkedin": bool(app_settings.linkedin_session_cookie),
            "glints": bool(app_settings.glints_session_cookie),
            "jobstreet": bool(app_settings.jobstreet_session_cookie),
        },
        "groq_configured": bool(app_settings.groq_api_key),
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


def extract_cookie_value(raw: str, cookie_name: str) -> str:
    """Pull a cookie value out of whatever the user pasted.

    Accepts a bare value, "name=value", a full Cookie header
    ("a=1; name=value; b=2"), or a DevTools table row ("name<TAB>value...").
    """
    import re
    raw = raw.strip().strip('"').strip()
    if not raw:
        return ""
    m = re.search(rf"(?:^|[;\s]){re.escape(cookie_name)}=([^;\s]+)", raw, re.IGNORECASE)
    if m:
        return m.group(1)
    # DevTools row paste: first column is the cookie name
    parts = raw.split()
    if len(parts) >= 2 and parts[0].lower() == cookie_name.lower():
        return parts[1]
    # Structured paste (other cookies, "a=1; b=2") that doesn't contain ours — refuse
    if ";" in raw or "=" in raw or len(parts) > 1:
        return ""
    return raw  # bare value


_COOKIE_NAMES = {"linkedin": "li_at", "glints": "token", "jobstreet": "JobseekerSessionToken"}

# ── Assisted login capture ───────────────────────────────────────────────────
# Opens a real (headed) browser; the user logs in normally and the session
# cookie is read from the browser context — no DevTools required.

_CAPTURE_CONFIG = {
    "linkedin": {
        "label": "LinkedIn",
        "login_url": "https://www.linkedin.com/login",
        "cookie": "li_at",
        "domain": "linkedin.com",
        "env": "LINKEDIN_SESSION_COOKIE",
        "attr": "linkedin_session_cookie",
    },
    "glints": {
        "label": "Glints",
        "login_url": "https://glints.com/id/login",
        "cookie": "token",
        "domain": "glints.com",
        "env": "GLINTS_SESSION_COOKIE",
        "attr": "glints_session_cookie",
    },
    "jobstreet": {
        "label": "JobStreet",
        "login_url": "https://id.jobstreet.com",
        "cookie": "JobseekerSessionToken",
        "domain": "jobstreet.com",
        "env": "JOBSTREET_SESSION_COOKIE",
        "attr": "jobstreet_session_cookie",
    },
}

_CAPTURE_TIMEOUT_SECONDS = 240

# Single capture at a time (single-user app). Mutate keys, never rebind.
_capture_state: dict = {"platform": None, "status": "idle", "error": None}


async def _capture_cookie(platform: str) -> None:
    cfg = _CAPTURE_CONFIG[platform]
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        _capture_state.update(status="error",
                              error="Playwright is not installed in the Python that runs this app. "
                                    "In the terminal where you start the app, run: "
                                    "pip install -r requirements.txt && playwright install chromium "
                                    "— then restart the app.")
        return

    value = None
    try:
        async with async_playwright() as p:
            # Hide the automation fingerprint: Google (and sometimes LinkedIn)
            # refuse to sign in when navigator.webdriver is set or the
            # "controlled by automated software" banner is present.
            launch_kwargs = dict(
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
                ignore_default_args=["--enable-automation"],
            )
            try:
                # Prefer the user's real Chrome install — looks like a normal browser.
                browser = await p.chromium.launch(channel="chrome", **launch_kwargs)
            except Exception:
                browser = await p.chromium.launch(**launch_kwargs)
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=30000)

            deadline = time.monotonic() + _CAPTURE_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                try:
                    cookies = await ctx.cookies()
                except Exception:
                    break  # user closed the window
                for c in cookies:
                    if c["name"] == cfg["cookie"] and cfg["domain"] in c.get("domain", ""):
                        value = c["value"]
                        break
                if value:
                    break
                await asyncio.sleep(1.5)
            await browser.close()
    except Exception as e:
        log.error("cookie_capture_failed", platform=platform, error=str(e))
        _capture_state.update(status="error", error=str(e))
        return

    if value:
        _update_env_file({cfg["env"]: value})
        setattr(app_settings, cfg["attr"], value)
        log.info("cookie_captured", platform=platform)
        _capture_state.update(status="done", error=None)
    else:
        _capture_state.update(
            status="error",
            error="No session cookie found — the window was closed or login took longer than 4 minutes. Try again.",
        )


@router.post("/cookies/capture/{platform}", response_class=HTMLResponse)
async def capture_start(platform: str, request: Request):
    if platform not in _CAPTURE_CONFIG:
        return HTMLResponse("Unknown platform", status_code=404)
    if _capture_state["status"] != "running":
        _capture_state.update(platform=platform, status="running", error=None)
        asyncio.get_running_loop().create_task(_capture_cookie(platform))
    return templates.TemplateResponse(request, "partials/cookie_capture_status.html",
                                      {"state": _capture_state, "config": _CAPTURE_CONFIG})


@router.get("/cookies/capture/status", response_class=HTMLResponse)
def capture_status(request: Request):
    return templates.TemplateResponse(request, "partials/cookie_capture_status.html",
                                      {"state": _capture_state, "config": _CAPTURE_CONFIG})


@router.post("/cookies/save", response_class=HTMLResponse)
async def cookies_save(
    request: Request,
    session: Session = Depends(get_session),
    linkedin_cookie: str = Form(""),
    glints_cookie: str = Form(""),
    jobstreet_cookie: str = Form(""),
):
    updates = {}
    pairs = [
        ("linkedin", linkedin_cookie, "LINKEDIN_SESSION_COOKIE", "linkedin_session_cookie"),
        ("glints", glints_cookie, "GLINTS_SESSION_COOKIE", "glints_session_cookie"),
        ("jobstreet", jobstreet_cookie, "JOBSTREET_SESSION_COOKIE", "jobstreet_session_cookie"),
    ]
    for platform, raw, env_key, attr in pairs:
        value = extract_cookie_value(raw, _COOKIE_NAMES[platform])
        if value:
            updates[env_key] = value
            setattr(app_settings, attr, value)
    if updates:
        _update_env_file(updates)
    log.info("cookies_updated", platforms=list(updates.keys()))
    return templates.TemplateResponse(request, "settings.html",
                                      _settings_ctx(request, session, cookies_saved=True))


@router.post("/groq/save", response_class=HTMLResponse)
async def groq_save(
    request: Request,
    session: Session = Depends(get_session),
    groq_api_key: str = Form(""),
):
    key = groq_api_key.strip()
    if key:
        _update_env_file({"GROQ_API_KEY": key})
        app_settings.groq_api_key = key
        log.info("groq_key_updated")
    return templates.TemplateResponse(request, "settings.html",
                                      _settings_ctx(request, session, groq_saved=True))


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

"""Phase 4: SMTP email sending with resume attachment."""
import smtplib
from email.message import EmailMessage
from pathlib import Path

from config import settings
from utils.logging import get_logger

log = get_logger(__name__)


def send_application_email(
    to: str,
    subject: str,
    body: str,
    resume_path: str | None = None,
    pdf_path: str | None = None,
) -> None:
    """Send application email via SMTP with optional resume attachment.

    Raises ValueError for missing config, smtplib.SMTPException or OSError on send failure.
    """
    if not settings.smtp_user or not settings.smtp_password:
        raise ValueError("SMTP credentials not configured — set SMTP_USER and SMTP_PASSWORD in .env")
    if not settings.from_email:
        raise ValueError("FROM_EMAIL not configured in .env")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = (
        f"{settings.from_name} <{settings.from_email}>" if settings.from_name else settings.from_email
    )
    msg["To"] = to
    msg.set_content(body)

    # Prefer PDF; fall back to DOCX
    attach = pdf_path or resume_path
    if attach:
        p = Path(attach)
        if p.exists():
            if p.suffix.lower() == ".pdf":
                maintype, subtype = "application", "pdf"
            else:
                maintype = "application"
                subtype = "vnd.openxmlformats-officedocument.wordprocessingml.document"
            msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)
        else:
            log.warning("resume_file_missing", path=attach)

    log.info("smtp_sending", to=to, subject=subject, host=settings.smtp_host)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

    log.info("email_sent", to=to, subject=subject)

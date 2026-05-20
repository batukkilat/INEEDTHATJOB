"""Phase 4: SMTP email sending with resume attachment."""
import smtplib
from email.message import EmailMessage
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
    """Send application email via SMTP. Phase 4 TODO."""
    raise NotImplementedError("Phase 4")

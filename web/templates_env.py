import json
import jinja2
from fastapi.templating import Jinja2Templates

_STATUS_LABELS = {
    "new": "New",
    "scored": "Scored",
    "generating": "Generating",
    "review_ready": "Ready to Review",
    "approved": "Approved",
    "applying": "Applying",
    "applied": "Applied",
    "skipped": "Skipped",
    "failed": "Failed",
    "pending_review": "Pending Review",
    "submitted": "Submitted",
    "rejected": "Rejected",
    "applied_manually": "Applied Manually",
}

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("web/templates"),
    autoescape=jinja2.select_autoescape(),
)
_env.filters["fromjson"] = json.loads
_env.filters["status_label"] = lambda s: _STATUS_LABELS.get(s, s.replace("_", " ").title() if s else "—")

templates = Jinja2Templates(env=_env)

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from web.templates_env import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def guide_page(request: Request):
    return templates.TemplateResponse(request, "guide.html", {"current_page": "guide"})

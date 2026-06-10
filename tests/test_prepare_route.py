"""The one-click Prepare route must generate all three artifacts and suggest a recipient."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from db.database import engine
from db.models import Application, Job
from main import app as fastapi_app


@pytest.fixture
def seeded_app():
    with Session(engine) as s:
        job = Job(platform="linkedin", external_id="prepare-test", url="http://example.com",
                  title="Backend Engineer", company="Acme",
                  description="Need Python. Kirim lamaran ke hr@acme.example.com",
                  compatibility_score=0.8, scraped_at="2026-06-10", status="review_ready")
        s.add(job)
        s.commit()
        s.refresh(job)
        appl = Application(job_id=job.id, apply_status="pending_review", created_at="2026-06-10")
        s.add(appl)
        s.commit()
        s.refresh(appl)
        yield appl.id
        s.delete(s.get(Application, appl.id))
        s.delete(s.get(Job, job.id))
        s.commit()


def test_prepare_generates_everything(seeded_app, monkeypatch):
    import web.routes.applications as routes

    async def fake_resume(job, session, profile=None):
        return "/tmp/fake.docx", {"summary": "S", "selected_skills": ["Python"], "experiences": []}

    async def fake_letter(job, session, profile=None):
        return "Dear hiring manager."

    async def fake_email(job, session, profile=None):
        return "Application – Backend Engineer", "Hello."

    import generation.resume
    monkeypatch.setattr(generation.resume, "generate_resume", fake_resume)
    monkeypatch.setattr(routes, "generate_cover_letter", fake_letter)
    monkeypatch.setattr(routes, "compose_email", fake_email)

    with TestClient(fastapi_app) as client:
        r = client.post(f"/review/{seeded_app}/prepare")
    assert r.status_code == 200
    assert "review-accordion" in r.text

    with Session(engine) as s:
        appl = s.get(Application, seeded_app)
        assert appl.resume_path == "/tmp/fake.docx"
        assert json.loads(appl.resume_content)["summary"] == "S"
        assert appl.cover_letter == "Dear hiring manager."
        assert appl.email_subject == "Application – Backend Engineer"
        assert appl.email_body == "Hello."
        assert appl.recipient_email == "hr@acme.example.com"

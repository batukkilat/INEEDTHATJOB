"""Regression: LLM generation must not block the event loop.

generate_cover_letter/compose_email previously called the synchronous
utils.llm.chat directly from async routes; a slow Groq call (or its
rate-limit backoff, up to minutes) froze every other request, including
the dashboard's pipeline-status polling.
"""
import asyncio
import time

from sqlmodel import SQLModel, Session, create_engine

from db.models import Job


def _make_job() -> Job:
    return Job(platform="linkedin", url="http://example.com", title="Backend Engineer",
               company="Acme", description="We need Python skills.", scraped_at="2026-01-01")


def _run_with_heartbeat(coro_factory) -> int:
    """Run the coroutine while counting event-loop heartbeats; return tick count."""
    ticks = 0

    async def main():
        nonlocal ticks

        async def heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        hb = asyncio.create_task(heartbeat())
        await coro_factory()
        hb.cancel()

    asyncio.run(main())
    return ticks


def test_generate_cover_letter_keeps_loop_responsive(monkeypatch):
    import generation.cover_letter as cl

    def slow_chat(**kwargs):
        time.sleep(0.3)
        return "Dear Hiring Manager, I am excited to apply."

    monkeypatch.setattr(cl, "chat", slow_chat)
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    job = _make_job()

    async def go():
        with Session(engine) as session:
            await cl.generate_cover_letter(job, session)

    ticks = _run_with_heartbeat(go)
    assert ticks >= 5, f"event loop starved during cover letter generation (ticks={ticks})"


def test_compose_email_keeps_loop_responsive(monkeypatch):
    import generation.email_composer as ec

    def slow_chat(**kwargs):
        time.sleep(0.3)
        return '{"subject": "Application", "body": "Hello."}'

    monkeypatch.setattr(ec, "chat", slow_chat)
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    job = _make_job()

    async def go():
        with Session(engine) as session:
            await ec.compose_email(job, session)

    ticks = _run_with_heartbeat(go)
    assert ticks >= 5, f"event loop starved during email composition (ticks={ticks})"

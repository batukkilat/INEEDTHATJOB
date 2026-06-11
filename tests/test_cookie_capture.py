"""Assisted login capture: route state machine and status partial."""
import asyncio

from fastapi.testclient import TestClient

import web.routes.settings as settings_routes
from main import app as fastapi_app


def _reset_state():
    settings_routes._capture_state.update(platform=None, status="idle", error=None)


def test_unknown_platform_404():
    _reset_state()
    with TestClient(fastapi_app) as c:
        r = c.post("/settings/cookies/capture/myspace")
    assert r.status_code == 404


def test_capture_start_spawns_task_and_polls(monkeypatch):
    _reset_state()
    started = []

    async def fake_capture(platform):
        started.append(platform)
        settings_routes._capture_state.update(status="done", error=None)

    monkeypatch.setattr(settings_routes, "_capture_cookie", fake_capture)
    with TestClient(fastapi_app) as c:
        r = c.post("/settings/cookies/capture/linkedin")
        assert r.status_code == 200
        assert "log in to LinkedIn" in r.text  # running state with poller
        assert 'hx-trigger="every 2s"' in r.text
        # TestClient runs the task on the same loop; give it a tick via a request
        r2 = c.get("/settings/cookies/capture/status")
    assert started == ["linkedin"]
    assert "captured and saved" in r2.text
    _reset_state()


def test_second_capture_ignored_while_running(monkeypatch):
    _reset_state()
    calls = []

    async def hang_capture(platform):
        calls.append(platform)
        await asyncio.sleep(30)

    monkeypatch.setattr(settings_routes, "_capture_cookie", hang_capture)
    with TestClient(fastapi_app) as c:
        c.post("/settings/cookies/capture/glints")
        c.post("/settings/cookies/capture/jobstreet")
    assert calls == ["glints"]
    _reset_state()

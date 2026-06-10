"""Regression: scheduled pipeline runs must honor SCRAPE_PLATFORMS from config.

run_pipeline() previously hardcoded ["linkedin"] when called without
arguments (the scheduler path), silently ignoring the configured platforms.
"""
from config import settings
from pipeline import _resolve_platforms


def test_explicit_platforms_win():
    assert _resolve_platforms(["glints"]) == ["glints"]


def test_defaults_come_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "scrape_platforms", '["jobstreet", "glints"]')
    assert _resolve_platforms(None) == ["jobstreet", "glints"]


def test_malformed_setting_falls_back_to_all_scrapers(monkeypatch):
    monkeypatch.setattr(settings, "scrape_platforms", "not json")
    assert _resolve_platforms(None) == ["linkedin", "glints", "jobstreet"]

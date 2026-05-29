"""Lightweight token-usage tracker backed by a JSON file.

Records per-day, per-model usage so the dashboard can show Groq quota meters
without requiring a DB migration or a live Groq API call.
"""
import json
import threading
from datetime import date
from pathlib import Path

from config import settings

_lock = threading.Lock()


def _path() -> Path:
    return Path(settings.db_path).parent / "llm_usage.json"


def _load() -> dict:
    p = _path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def record(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    today = date.today().isoformat()
    with _lock:
        data = _load()
        day = data.setdefault(today, {})
        entry = day.setdefault(model, {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0})
        entry["prompt_tokens"] += prompt_tokens
        entry["completion_tokens"] += completion_tokens
        entry["calls"] += 1
        _path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_today() -> dict:
    """Return {model: {prompt_tokens, completion_tokens, calls}} for today."""
    return _load().get(date.today().isoformat(), {})


def get_history(days: int = 7) -> dict:
    """Return usage dict for the last N calendar days (keyed by ISO date)."""
    data = _load()
    sorted_keys = sorted(data.keys(), reverse=True)
    return {k: data[k] for k in sorted_keys[:days]}

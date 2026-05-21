import json
import time
import httpx
from config import settings
from utils.logging import get_logger

log = get_logger(__name__)

GROQ_BASE = "https://api.groq.com/openai/v1"


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"}


def _post(payload: dict, max_retries: int = 4) -> dict:
    """POST to Groq with exponential backoff on 429/503."""
    delay = 5
    for attempt in range(max_retries):
        r = httpx.post(f"{GROQ_BASE}/chat/completions", json=payload, headers=_headers(), timeout=60)
        if r.status_code == 429 or r.status_code == 503:
            retry_after = int(r.headers.get("retry-after", delay))
            wait = max(retry_after, delay)
            log.warning("llm_rate_limited", status=r.status_code, wait=wait, attempt=attempt + 1)
            time.sleep(wait)
            delay = min(delay * 2, 60)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def chat(model: str, messages: list[dict], system: str = "", max_tokens: int = 2048, **kwargs) -> str:
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    data = _post({"model": model, "messages": msgs, "max_tokens": max_tokens})
    content = data["choices"][0]["message"]["content"]
    log.info("llm_call", model=model, tokens=data.get("usage", {}).get("completion_tokens"))
    return content


def chat_with_tool(model: str, messages: list[dict], tool_name: str, tool_schema: dict,
                   system: str = "", max_tokens: int = 2048) -> dict:
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    tool = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_schema.get("description", ""),
            "parameters": tool_schema["input_schema"],
        },
    }
    payload = {
        "model": model,
        "messages": msgs,
        "tools": [tool],
        "tool_choice": {"type": "function", "function": {"name": tool_name}},
        "max_tokens": max_tokens,
    }
    data = _post(payload)
    log.info("llm_tool_call", model=model, tool=tool_name, tokens=data.get("usage", {}).get("completion_tokens"))

    msg = data["choices"][0]["message"]
    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        args = tool_calls[0]["function"]["arguments"]
        return json.loads(args) if isinstance(args, str) else args

    # Fallback: parse JSON from text
    text = msg.get("content", "")
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass

    log.warning("tool_call_parse_failed", response=text[:200])
    return {}

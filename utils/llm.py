import json
import time
import httpx
from config import settings
from utils.logging import get_logger

log = get_logger(__name__)

GROQ_BASE = "https://api.groq.com/openai/v1"


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of an LLM text response. None if unparseable."""
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"}


def _post(payload: dict, max_retries: int = 6) -> dict:
    """POST to Groq with exponential backoff on 429/503."""
    delay = 5
    for attempt in range(max_retries):
        r = httpx.post(f"{GROQ_BASE}/chat/completions", json=payload, headers=_headers(), timeout=60)
        if r.status_code == 429 or r.status_code == 503:
            retry_after = int(r.headers.get("retry-after", delay))
            wait = max(retry_after, delay)
            log.warning("llm_rate_limited", status=r.status_code, wait=wait, attempt=attempt + 1)
            # Sleep in 1s chunks so stop button is responsive during backoff
            for _ in range(int(wait)):
                try:
                    from pipeline import stop_requested
                    if stop_requested():
                        raise InterruptedError("stop requested during backoff")
                except ImportError:
                    pass
                time.sleep(1)
            delay = min(delay * 2, 120)
            continue
        # Groq returns 400 tool_use_failed when a weak model emits a malformed tool call;
        # the usable generation is in error.failed_generation — return it for the caller to salvage.
        if r.status_code == 400 and r.json().get("error", {}).get("code") == "tool_use_failed":
            return r.json()
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def chat(model: str, messages: list[dict], system: str = "", max_tokens: int = 2048,
         temperature: float = 1.0, **kwargs) -> str:
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    data = _post({"model": model, "messages": msgs, "max_tokens": max_tokens,
                  "temperature": temperature})
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    log.info("llm_call", model=model, tokens=usage.get("completion_tokens"))
    if usage:
        from utils import usage_tracker
        usage_tracker.record(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
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

    # Salvage a malformed tool call (Groq 400 tool_use_failed): JSON is in failed_generation.
    if "error" in data:
        failed = data["error"].get("failed_generation", "")
        parsed = extract_json(failed)
        if parsed is not None:
            log.info("llm_tool_call_salvaged", model=model, tool=tool_name)
            return parsed
        log.warning("tool_call_parse_failed", response=failed[:200])
        return {}

    tool_usage = data.get("usage", {})
    log.info("llm_tool_call", model=model, tool=tool_name, tokens=tool_usage.get("completion_tokens"))
    if tool_usage:
        from utils import usage_tracker
        usage_tracker.record(model, tool_usage.get("prompt_tokens", 0), tool_usage.get("completion_tokens", 0))

    msg = data["choices"][0]["message"]
    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        args = tool_calls[0]["function"]["arguments"]
        return json.loads(args) if isinstance(args, str) else args

    # Fallback: parse JSON from text
    text = msg.get("content", "")
    parsed = extract_json(text)
    if parsed is not None:
        return parsed

    log.warning("tool_call_parse_failed", response=text[:200])
    return {}

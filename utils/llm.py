import json
import httpx
from config import settings
from utils.logging import get_logger

log = get_logger(__name__)

OLLAMA_BASE = "http://127.0.0.1:11434/api"


def chat(model: str, messages: list[dict], system: str = "", max_tokens: int = 2048, **kwargs) -> str:
    """Simple text completion via Ollama."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    if system:
        payload["system"] = system

    r = httpx.post(f"{OLLAMA_BASE}/chat", json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    content = data["message"]["content"]
    log.info("llm_call", model=model, tokens=data.get("eval_count"))
    return content


def chat_with_tool(model: str, messages: list[dict], tool_name: str, tool_schema: dict,
                   system: str = "", max_tokens: int = 2048) -> dict:
    """Structured extraction via Ollama tool calling. Returns the tool input dict."""
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
        "messages": messages,
        "tools": [tool],
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    if system:
        payload["system"] = system

    r = httpx.post(f"{OLLAMA_BASE}/chat", json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    log.info("llm_tool_call", model=model, tool=tool_name, tokens=data.get("eval_count"))

    # Extract tool call result
    msg = data.get("message", {})
    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        return tool_calls[0].get("function", {}).get("arguments", {})

    # Fallback: try to parse JSON from the text response
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

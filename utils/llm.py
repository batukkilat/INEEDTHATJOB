import anthropic
from config import settings
from utils.logging import get_logger

log = get_logger(__name__)

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def chat(model: str, messages: list[dict], system: str = "", max_tokens: int = 2048, **kwargs) -> str:
    """Simple text completion."""
    client = get_client()
    kwargs_full = dict(model=model, messages=messages, max_tokens=max_tokens, **kwargs)
    if system:
        kwargs_full["system"] = system
    response = client.messages.create(**kwargs_full)
    log.info("llm_call", model=model, input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens)
    return response.content[0].text


def chat_with_tool(model: str, messages: list[dict], tool_name: str, tool_schema: dict,
                   system: str = "", max_tokens: int = 1024) -> dict:
    """Structured extraction via forced tool use. Returns the tool input dict."""
    client = get_client()
    tool = {"name": tool_name, "description": tool_schema.get("description", ""), "input_schema": tool_schema["input_schema"]}
    kwargs: dict = dict(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
    )
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    log.info("llm_tool_call", model=model, tool=tool_name,
             input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens)
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    return {}

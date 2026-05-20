from openai import OpenAI
from config import settings
from utils.logging import get_logger

log = get_logger(__name__)

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def chat(model: str, messages: list[dict], temperature: float = 0, **kwargs) -> str:
    client = get_client()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        **kwargs,
    )
    usage = response.usage
    log.info("llm_call", model=model, input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens)
    return response.choices[0].message.content

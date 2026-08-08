"""Клиент Gemini API. Имя модели берётся из настроек, не зашито в бизнес-логику."""
import asyncio

from google import genai
from google.genai import types

from app.config import get_settings


class AIError(Exception):
    pass


async def generate(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> dict:
    """Возвращает {'text', 'model', 'input_tokens', 'output_tokens'}. Бросает AIError."""
    s = get_settings()
    model = model or s.ai_model_primary
    client = genai.Client(api_key=s.gemini_api_key)
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=s.ai_temperature,
                    max_output_tokens=max_output_tokens or s.ai_max_output_tokens,
                ),
            ),
            timeout=s.ai_timeout_seconds,
        )
    except asyncio.TimeoutError as e:
        raise AIError("AI request timed out") from e
    except Exception as e:
        raise AIError(str(e)) from e

    text = getattr(response, "text", None)
    if not text:
        raise AIError("Empty AI response")

    usage = getattr(response, "usage_metadata", None)
    return {
        "text": text,
        "model": model,
        "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
    }

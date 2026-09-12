"""Асинхронный клиент OpenAI Responses API."""
import asyncio

from openai import AsyncOpenAI

from app.config import get_settings


class AIError(Exception):
    """Ошибка генерации ответа ИИ."""


async def generate(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> dict:
    """Возвращает текст ответа, модель и фактический расход токенов."""
    settings = get_settings()
    selected_model = model or settings.ai_model_primary
    if not settings.openai_api_key:
        raise AIError("OPENAI_API_KEY is not configured")
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        response = await asyncio.wait_for(
            client.responses.create(
                model=selected_model,
                instructions=system_prompt,
                input=user_prompt,
                max_output_tokens=max_output_tokens or settings.ai_max_output_tokens,
                temperature=settings.ai_temperature,
                store=False,
            ),
            timeout=settings.ai_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise AIError("AI request timed out") from exc
    except Exception as exc:
        raise AIError(str(exc)) from exc
    finally:
        await client.close()

    text = response.output_text
    if not text:
        raise AIError("Empty AI response")

    usage = response.usage
    return {
        "text": text,
        "model": response.model or selected_model,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
    }

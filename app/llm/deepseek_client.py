from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from app.observability.langfuse_observability_v2 import (
    start_safe_generation_v2,
    update_safe_generation_usage_v2,
    update_safe_observation_v2,
)


load_dotenv()


DEEPSEEK_MODEL = os.getenv(
    "DEEPSEEK_MODEL",
    "deepseek-v4-pro",
).strip()

if not DEEPSEEK_MODEL:
    raise RuntimeError(
        "DEEPSEEK_MODEL cannot be empty."
    )


@lru_cache(maxsize=1)
def get_deepseek_client() -> OpenAI:
    """
    Return the shared OpenAI-compatible DeepSeek client.

    Client creation is lazy:
    importing a module must not require a live API connection.
    """
    api_key = os.getenv(
        "DEEPSEEK_API_KEY"
    )
    base_url = os.getenv(
        "DEEPSEEK_BASE_URL"
    )

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


def chat_completion(
    *,
    messages: list[dict[str, str]],
    temperature: float = 0,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    """
    Minimal shared LLM transport.

    Responsibilities:
    - model selection
    - OpenAI-compatible client invocation
    - raw assistant text extraction

    Deliberately NOT responsible for:
    - prompts
    - JSON parsing
    - business validation
    - retry policy
    - SQL cleaning
    - metric selection
    """
    actual_model = (
        model
        if model is not None
        else DEEPSEEK_MODEL
    )

    if not actual_model:
        raise RuntimeError(
            "LLM model cannot be empty."
        )

    actual_client = (
        client
        if client is not None
        else get_deepseek_client()
    )

    with start_safe_generation_v2(
        name="deepseek_chat_completion",
        model=actual_model,
        stage="llm_transport",
    ) as generation:
        response = (
            actual_client
            .chat
            .completions
            .create(
                model=actual_model,
                messages=messages,
                temperature=temperature,
            )
        )

        usage = getattr(
            response,
            "usage",
            None,
        )

        update_safe_generation_usage_v2(
            generation,
            prompt_tokens=(
                getattr(usage, "prompt_tokens", None)
                if usage is not None
                else None
            ),
            completion_tokens=(
                getattr(usage, "completion_tokens", None)
                if usage is not None
                else None
            ),
            total_tokens=(
                getattr(usage, "total_tokens", None)
                if usage is not None
                else None
            ),
        )

        update_safe_observation_v2(
            generation,
            status="success",
        )

        return (
            response.choices[0].message.content
            or ""
        )

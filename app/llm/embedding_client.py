from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Sequence

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


AI_EMBEDDING_MODEL = os.getenv(
    "AI_EMBEDDING_MODEL",
    "",
).strip()


class EmbeddingTransportError(RuntimeError):
    """
    Embedding Transport 的 fail-closed 异常。

    这里只表达 Transport / response contract 失败，
    不负责决定 Semantic Layer 应如何降级。
    """


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise EmbeddingTransportError(
            f"Missing required environment variable: {name}"
        )

    return value.strip()


@lru_cache(maxsize=1)
def get_embedding_client() -> OpenAI:
    """
    返回共享的 OpenAI-compatible Embedding Client。

    Client 创建保持 lazy：
    仅 import 模块不会访问真实网络，也不会要求 API Key 已经存在。
    """

    return OpenAI(
        api_key=_required_env(
            "AI_EMBEDDING_API_KEY"
        ),
        base_url=_required_env(
            "AI_EMBEDDING_BASE_URL"
        ),
    )


def _resolve_model(
    model: str | None,
) -> str:
    actual_model = (
        model.strip()
        if model is not None
        else AI_EMBEDDING_MODEL
    )

    if not actual_model:
        raise EmbeddingTransportError(
            "Embedding model cannot be empty. "
            "Set AI_EMBEDDING_MODEL or pass model explicitly."
        )

    return actual_model


def _validate_inputs(
    texts: Sequence[str],
) -> tuple[str, ...]:
    normalized = tuple(texts)

    if not normalized:
        raise EmbeddingTransportError(
            "Embedding input cannot be empty."
        )

    if any(
        not isinstance(text, str)
        or not text.strip()
        for text in normalized
    ):
        raise EmbeddingTransportError(
            "Every embedding input must be a non-empty string."
        )

    return normalized


def create_embeddings(
    *,
    texts: Sequence[str],
    model: str | None = None,
    client: Any | None = None,
) -> list[list[float]]:
    """
    最小 OpenAI-compatible Embedding Transport。

    Responsibilities:
    - model selection
    - batch input validation
    - lazy client selection
    - OpenAI-compatible embeddings invocation
    - response ordering / shape validation
    - 返回普通 Python float vectors

    Deliberately NOT responsible for:
    - metric candidate ranking
    - cosine similarity
    - vector cache
    - provider selection policy
    - Semantic Decision / Clarification
    """

    normalized_texts = _validate_inputs(
        texts
    )
    actual_model = _resolve_model(
        model
    )
    actual_client = (
        client
        if client is not None
        else get_embedding_client()
    )

    response = (
        actual_client
        .embeddings
        .create(
            model=actual_model,
            input=list(
                normalized_texts
            ),
        )
    )

    data = list(
        getattr(
            response,
            "data",
            (),
        )
    )

    if len(data) != len(normalized_texts):
        raise EmbeddingTransportError(
            "Embedding response count does not match input count."
        )

    try:
        ordered = sorted(
            data,
            key=lambda item: int(
                item.index
            ),
        )
    except Exception as error:
        raise EmbeddingTransportError(
            "Embedding response items must expose valid indexes."
        ) from error

    expected_indexes = list(
        range(
            len(normalized_texts)
        )
    )
    actual_indexes = [
        int(item.index)
        for item in ordered
    ]

    if actual_indexes != expected_indexes:
        raise EmbeddingTransportError(
            "Embedding response indexes are incomplete or duplicated."
        )

    vectors: list[list[float]] = []

    for item in ordered:
        raw_vector = getattr(
            item,
            "embedding",
            None,
        )

        if not raw_vector:
            raise EmbeddingTransportError(
                "Embedding response contains an empty vector."
            )

        try:
            vector = [
                float(value)
                for value in raw_vector
            ]
        except Exception as error:
            raise EmbeddingTransportError(
                "Embedding vector must contain numeric values."
            ) from error

        vectors.append(
            vector
        )

    dimensions = {
        len(vector)
        for vector in vectors
    }

    if (
        not dimensions
        or 0 in dimensions
        or len(dimensions) != 1
    ):
        raise EmbeddingTransportError(
            "Embedding vectors must have one consistent non-zero dimension."
        )

    return vectors

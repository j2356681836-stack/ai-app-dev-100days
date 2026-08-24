from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Callable, Sequence


LOCAL_EMBEDDING_PROVIDER = "local"
OPENAI_COMPATIBLE_EMBEDDING_PROVIDER = "openai_compatible"
DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

SUPPORTED_EMBEDDING_PROVIDERS = frozenset(
    {
        LOCAL_EMBEDDING_PROVIDER,
        OPENAI_COMPATIBLE_EMBEDDING_PROVIDER,
    }
)


class EmbeddingServiceError(RuntimeError):
    """
    Provider-neutral Embedding Service 异常。

    这一层只负责 Embedding Runtime / vector contract，
    不负责决定 Semantic Layer 的 clarification / fallback 行为。
    """


RemoteEmbedder = Callable[..., list[list[float]]]


def resolve_embedding_provider(
    provider: str | None = None,
) -> str:
    """
    解析当前 Embedding Provider。

    默认保持 local，确保未配置云端 Provider 时，
    现有本地学习 / Evaluation 行为不被静默改变。
    """

    actual_provider = (
        provider
        if provider is not None
        else os.getenv(
            "AI_EMBEDDING_PROVIDER",
            LOCAL_EMBEDDING_PROVIDER,
        )
    ).strip().lower()

    if actual_provider not in SUPPORTED_EMBEDDING_PROVIDERS:
        raise EmbeddingServiceError(
            "Unsupported AI_EMBEDDING_PROVIDER: "
            f"{actual_provider}"
        )

    return actual_provider


def resolve_embedding_model(
    *,
    provider: str,
    model: str | None = None,
) -> str:
    """
    解析 Provider 对应的模型名称。

    local:
    - 显式 model
    - AI_EMBEDDING_MODEL
    - DEFAULT_LOCAL_EMBEDDING_MODEL

    openai_compatible:
    - 显式 model
    - AI_EMBEDDING_MODEL
    - 缺失时 fail closed
    """

    configured = os.getenv(
        "AI_EMBEDDING_MODEL",
        "",
    ).strip()

    if model is not None:
        actual_model = model.strip()
    elif configured:
        actual_model = configured
    elif provider == LOCAL_EMBEDDING_PROVIDER:
        actual_model = DEFAULT_LOCAL_EMBEDDING_MODEL
    else:
        actual_model = ""

    if not actual_model:
        raise EmbeddingServiceError(
            "Embedding model cannot be empty. "
            "Set AI_EMBEDDING_MODEL or pass model explicitly."
        )

    return actual_model


def _normalize_texts(
    texts: Sequence[str],
) -> tuple[str, ...]:
    normalized = tuple(
        texts
    )

    if not normalized:
        raise EmbeddingServiceError(
            "Embedding input cannot be empty."
        )

    if any(
        not isinstance(text, str)
        or not text.strip()
        for text in normalized
    ):
        raise EmbeddingServiceError(
            "Every embedding input must be a non-empty string."
        )

    return normalized


def _normalize_vectors(
    vectors: Any,
    *,
    expected_count: int,
) -> list[list[float]]:
    """
    将 numpy/list 等实现结果统一收敛成普通 Python float vectors。
    """

    if hasattr(
        vectors,
        "tolist",
    ):
        vectors = vectors.tolist()

    try:
        normalized = [
            [
                float(value)
                for value in vector
            ]
            for vector in vectors
        ]
    except Exception as error:
        raise EmbeddingServiceError(
            "Embedding runtime returned invalid vectors."
        ) from error

    if len(normalized) != expected_count:
        raise EmbeddingServiceError(
            "Embedding vector count does not match input count."
        )

    dimensions = {
        len(vector)
        for vector in normalized
    }

    if (
        not dimensions
        or 0 in dimensions
        or len(dimensions) != 1
    ):
        raise EmbeddingServiceError(
            "Embedding vectors must have one consistent non-zero dimension."
        )

    return normalized


@lru_cache(maxsize=4)
def _load_local_model_cached(
    model_name: str,
):
    """
    真正的 sentence-transformers import 只发生在 local Provider
    第一次需要模型时，避免模块 import 阶段加载 PyTorch。
    """

    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        model_name,
        local_files_only=True,
    )


def load_model(
    model_name: str | None = None,
):
    """
    保留旧的 Local BGE load_model() 调用入口。

    默认仍使用 BAAI/bge-small-zh-v1.5；
    模型对象按 model_name 缓存。
    """

    actual_model = resolve_embedding_model(
        provider=LOCAL_EMBEDDING_PROVIDER,
        model=model_name,
    )

    return _load_local_model_cached(
        actual_model
    )


def _create_remote_embeddings(
    *,
    texts: Sequence[str],
    model: str,
) -> list[list[float]]:
    """
    Lazy import OpenAI-compatible Transport。

    Remote Provider 不需要加载 sentence-transformers / PyTorch。
    """

    from app.llm.embedding_client import (
        create_embeddings,
    )

    return create_embeddings(
        texts=texts,
        model=model,
    )


def embed_texts(
    texts: Sequence[str],
    *,
    provider: str | None = None,
    model: str | None = None,
    local_model: Any | None = None,
    remote_embedder: RemoteEmbedder | None = None,
) -> list[list[float]]:
    """
    Provider-neutral batch Embedding facade。

    local:
    - lazy load SentenceTransformer
    - 一次 model.encode(list[str])

    openai_compatible:
    - 调用 app.llm.embedding_client
    - 一次 batch embeddings request

    local_model / remote_embedder 仅用于依赖注入测试，
    正式运行时调用方无需传入。
    """

    normalized_texts = _normalize_texts(
        texts
    )
    actual_provider = resolve_embedding_provider(
        provider
    )
    actual_model = resolve_embedding_model(
        provider=actual_provider,
        model=model,
    )

    if (
        actual_provider
        == LOCAL_EMBEDDING_PROVIDER
    ):
        actual_local_model = (
            local_model
            if local_model is not None
            else load_model(
                actual_model
            )
        )

        raw_vectors = (
            actual_local_model
            .encode(
                list(
                    normalized_texts
                )
            )
        )

        return _normalize_vectors(
            raw_vectors,
            expected_count=len(
                normalized_texts
            ),
        )

    actual_remote_embedder = (
        remote_embedder
        if remote_embedder is not None
        else _create_remote_embeddings
    )

    raw_vectors = actual_remote_embedder(
        texts=normalized_texts,
        model=actual_model,
    )

    return _normalize_vectors(
        raw_vectors,
        expected_count=len(
            normalized_texts
        ),
    )


def embed_text(
    text: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    local_model: Any | None = None,
    remote_embedder: RemoteEmbedder | None = None,
) -> list[float]:
    """
    向后兼容的单文本入口。

    现有 Semantic Search 调用方可以继续使用 embed_text(text)；
    新的 Metric Vector Cache 可以改用 embed_texts() 做 batch。
    """

    return embed_texts(
        [
            text,
        ],
        provider=provider,
        model=model,
        local_model=local_model,
        remote_embedder=remote_embedder,
    )[0]

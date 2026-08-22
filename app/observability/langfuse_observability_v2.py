from __future__ import annotations

import os
from contextlib import contextmanager
from enum import Enum
from typing import Any, Iterator

from langfuse import get_client


# Observability 必须显式开启。
_ENABLED_ENV = "LANGFUSE_OBSERVABILITY_ENABLED"

_REQUIRED_LANGFUSE_ENV_VARS = (
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_BASE_URL",
)

_TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "on",
}


# 只允许明确审核过的 metadata key。
#
# 特意不包含：
# question / prompt / sql / parameters / rows /
# access_context / evidence_payload / secret 等原始内容。
_SAFE_METADATA_KEYS_V2 = frozenset(
    {
        "stage",
        "request_id",
        "round_number",
        "action_id",
        "decision_type",
        "status",
        "reason_code",
        "directive",
        "stop_reason",
        "row_count",
        "released_row_count",
        "retryable",
        "attempt_number",
        "model",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "metric_name",
        "evidence_count",
        "sufficiency",
        "purpose",
    }
)


def langfuse_observability_enabled_v2() -> bool:
    """
    Langfuse Observability 是否显式开启且配置完整。

    Observability 是旁路能力。
    缺少配置时，不应该让核心业务 Runtime 无法运行。
    """
    enabled = (
        os.getenv(_ENABLED_ENV, "")
        .strip()
        .lower()
        in _TRUE_VALUES
    )

    if not enabled:
        return False

    return all(
        bool(os.getenv(name))
        for name in _REQUIRED_LANGFUSE_ENV_VARS
    )


def build_safe_metadata_v2(
    **values: Any,
) -> dict[str, str]:
    """
    建立允许发送到外部 Observability 平台的安全 metadata。

    规则：
    - 不接受未审核的 key；
    - 不接受复杂对象；
    - 不接受超过 200 字符的值；
    - Enum 只发送 value；
    - 不发送 None。
    """
    unknown_keys = (
        set(values)
        - _SAFE_METADATA_KEYS_V2
    )

    if unknown_keys:
        raise ValueError(
            "Unsafe observability metadata keys: "
            + ", ".join(sorted(unknown_keys))
        )

    metadata: dict[str, str] = {}

    for key, value in values.items():
        if value is None:
            continue

        if isinstance(value, Enum):
            value = value.value

        if isinstance(value, bool):
            text = (
                "true"
                if value
                else "false"
            )
        elif isinstance(
            value,
            (str, int, float),
        ):
            text = str(value)
        else:
            raise TypeError(
                "Observability metadata only accepts "
                "str / int / float / bool / Enum. "
                f"key={key}"
            )

        if len(text) > 200:
            raise ValueError(
                "Observability metadata value exceeds "
                f"200 characters. key={key}"
            )

        metadata[key] = text

    return metadata


@contextmanager
def start_safe_span_v2(
    *,
    name: str,
    **metadata: Any,
) -> Iterator[Any | None]:
    """
    创建一个不自动捕获业务 input/output 的 Langfuse Span。

    Langfuse 未开启时退化为 no-op。
    """
    if not langfuse_observability_enabled_v2():
        yield None
        return

    safe_metadata = build_safe_metadata_v2(
        **metadata
    )

    langfuse = get_client()

    with langfuse.start_as_current_observation(
        as_type="span",
        name=name,
        metadata=safe_metadata,
    ) as span:
        yield span


@contextmanager
def start_safe_generation_v2(
    *,
    name: str,
    model: str,
    **metadata: Any,
) -> Iterator[Any | None]:
    """
    创建 LLM Generation Observation。

    不自动上传 prompt / response；
    后续只显式更新安全的 model / usage / status。
    """
    if not langfuse_observability_enabled_v2():
        yield None
        return

    safe_metadata = build_safe_metadata_v2(
        **metadata
    )

    langfuse = get_client()

    with langfuse.start_as_current_observation(
        as_type="generation",
        name=name,
        model=model,
        metadata=safe_metadata,
    ) as generation:
        yield generation


def update_safe_observation_v2(
    observation: Any | None,
    **metadata: Any,
) -> None:
    """
    仅使用安全 allowlist metadata 更新已有 Observation。

    不写入 input / output / raw payload。
    Observability 关闭时 observation 为 None，直接 no-op。
    """
    if observation is None:
        return

    safe_metadata = build_safe_metadata_v2(
        **metadata
    )

    if not safe_metadata:
        return

    observation.update(
        metadata=safe_metadata,
    )


def update_safe_generation_usage_v2(
    generation: Any | None,
    *,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> None:
    """
    将 provider 返回的 OpenAI-compatible token usage 写入 Generation。

    这里只允许 token count；不上传 prompt / completion 内容。
    Langfuse 支持 OpenAI-style usage_details：
    prompt_tokens / completion_tokens / total_tokens。
    """
    if generation is None:
        return

    usage_details: dict[str, int] = {}

    for key, value in (
        ("prompt_tokens", prompt_tokens),
        ("completion_tokens", completion_tokens),
        ("total_tokens", total_tokens),
    ):
        if value is None:
            continue

        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                "Generation token usage must be int or None. "
                f"key={key}"
            )

        if value < 0:
            raise ValueError(
                "Generation token usage cannot be negative. "
                f"key={key}"
            )

        usage_details[key] = value

    if not usage_details:
        return

    generation.update(
        usage_details=usage_details,
    )


def flush_langfuse_v2() -> None:
    """
    仅供短生命周期脚本 / Acceptance 使用。

    正常在线请求不要每次强制 flush，
    否则会把 Observability 网络开销加入业务 latency。
    """
    if not langfuse_observability_enabled_v2():
        return

    get_client().flush()

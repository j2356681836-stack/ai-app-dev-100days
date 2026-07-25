import os
from pathlib import Path
from typing import Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)


class GovernanceRuntimeConfig(BaseModel):
    """
    Day71 治理运行时配置。

    SecretStr 防止 Secret 出现在 repr 和 JSON 中。
    真实 Secret 只能通过 get_secret_value() 在最小调用边界读取。
    """

    model_config = ConfigDict(frozen=True)

    result_tokenization_secret: SecretStr
    audit_secret: SecretStr
    audit_log_path: Path

    create_parent_directory: bool = True
    fsync_enabled: bool = True

    config_version: str = "governance_runtime_v1"

    @field_validator(
        "result_tokenization_secret",
        "audit_secret",
    )
    @classmethod
    def validate_secret(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        if len(value.get_secret_value()) < 16:
            raise ValueError(
                "Governance secrets must contain at least "
                "16 characters."
            )

        return value

    @field_validator("audit_log_path")
    @classmethod
    def validate_audit_log_path(
        cls,
        value: Path,
    ) -> Path:
        if value.suffix.lower() != ".jsonl":
            raise ValueError(
                "audit_log_path must use the .jsonl suffix."
            )

        return value

    @field_validator("config_version")
    @classmethod
    def validate_config_version(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "config_version cannot be empty."
            )

        return value


class GovernanceConfigurationError(RuntimeError):
    pass


def _required_env(
    env: Mapping[str, str],
    name: str,
) -> str:
    value = env.get(name)

    if value is None or not value.strip():
        raise GovernanceConfigurationError(
            f"Missing required environment variable: {name}"
        )

    return value


def load_governance_runtime_config(
    env: Mapping[str, str] | None = None,
) -> GovernanceRuntimeConfig:
    source = env if env is not None else os.environ

    try:
        return GovernanceRuntimeConfig(
            result_tokenization_secret=(
                _required_env(
                    source,
                    "AI_RESULT_TOKENIZATION_SECRET",
                )
            ),
            audit_secret=_required_env(
                source,
                "AI_AUDIT_SECRET",
            ),
            audit_log_path=Path(
                _required_env(
                    source,
                    "AI_AUDIT_LOG_PATH",
                )
            ),
        )
    except GovernanceConfigurationError:
        raise
    except Exception as error:
        raise GovernanceConfigurationError(
            "Invalid governance runtime configuration."
        ) from error

from __future__ import annotations

import re
from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.db.beauty_bi_v2.manifest_loader import (
    load_and_validate_day64_manifest,
)


class RequestedScopeResolutionStatusV2(str, Enum):
    """
    用户 Requested Scope 的确定性解析状态。
    """

    NO_EXPLICIT_SCOPE = "no_explicit_scope"
    RESOLVED = "resolved"
    UNRESOLVED_EXPLICIT_SCOPE = (
        "unresolved_explicit_scope"
    )


class RequestedScopeDimensionV2(str, Enum):
    REGION = "region"
    CHANNEL = "channel"


class RequestedScopeResolutionV2(BaseModel):
    """
    用户原始问题中的 Requested Scope。

    注意：
    - 这里表达的是“用户这次想查什么”；
    - 不表达“用户有权查什么”；
    - 因此不能替代 AccessContext；
    - 这里也不生成 SQL。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: RequestedScopeResolutionStatusV2

    region_codes: frozenset[str] = frozenset()
    channel_codes: frozenset[str] = frozenset()

    matched_region_terms: tuple[str, ...] = ()
    matched_channel_terms: tuple[str, ...] = ()

    unresolved_dimensions: frozenset[
        RequestedScopeDimensionV2
    ] = frozenset()

    @model_validator(mode="after")
    def validate_resolution(
        self,
    ) -> "RequestedScopeResolutionV2":
        has_scope = bool(
            self.region_codes
            or self.channel_codes
        )

        if (
            self.status
            == RequestedScopeResolutionStatusV2.NO_EXPLICIT_SCOPE
        ):
            if has_scope:
                raise ValueError(
                    "NO_EXPLICIT_SCOPE must not expose scope codes."
                )

            if (
                self.matched_region_terms
                or self.matched_channel_terms
            ):
                raise ValueError(
                    "NO_EXPLICIT_SCOPE must not expose matched terms."
                )

            if self.unresolved_dimensions:
                raise ValueError(
                    "NO_EXPLICIT_SCOPE must not expose unresolved "
                    "dimensions."
                )

        if (
            self.status
            == RequestedScopeResolutionStatusV2.RESOLVED
        ):
            if not has_scope:
                raise ValueError(
                    "RESOLVED requires at least one scope code."
                )

            if self.unresolved_dimensions:
                raise ValueError(
                    "RESOLVED must not expose unresolved dimensions."
                )

        if (
            self.status
            == RequestedScopeResolutionStatusV2
            .UNRESOLVED_EXPLICIT_SCOPE
        ):
            if not self.unresolved_dimensions:
                raise ValueError(
                    "UNRESOLVED_EXPLICIT_SCOPE requires at least "
                    "one unresolved dimension."
                )

        return self


def _normalize_text(
    value: str,
) -> str:
    return re.sub(
        r"\s+",
        "",
        str(value),
    ).casefold()


def _strip_controlled_suffix(
    value: str,
    suffixes: tuple[str, ...],
) -> str | None:
    for suffix in sorted(
        suffixes,
        key=len,
        reverse=True,
    ):
        if (
            value.endswith(suffix)
            and len(value) > len(suffix)
        ):
            return value[:-len(suffix)]

    return None


def _add_alias(
    mapping: dict[str, set[str]],
    *,
    alias: str,
    code: str,
) -> None:
    normalized_alias = _normalize_text(alias)
    normalized_code = str(code).strip()

    if not normalized_alias or not normalized_code:
        return

    mapping.setdefault(
        normalized_alias,
        set(),
    ).add(normalized_code)


@lru_cache(maxsize=1)
def _build_scope_alias_catalog_v2() -> tuple[
    dict[str, frozenset[str]],
    dict[str, frozenset[str]],
]:
    manifest: dict[str, Any] = (
        load_and_validate_day64_manifest()
    )

    fixed_dimensions = manifest["fixed_dimensions"]

    region_aliases: dict[str, set[str]] = {}
    channel_aliases: dict[str, set[str]] = {}

    for region in fixed_dimensions["regions"]:
        region_code = region["region_code"].strip()
        region_name = region["region_name"].strip()
        province_name = region["province_name"].strip()

        _add_alias(
            region_aliases,
            alias=region_code,
            code=region_code,
        )
        _add_alias(
            region_aliases,
            alias=region_name,
            code=region_code,
        )

        short_region_name = _strip_controlled_suffix(
            region_name,
            (
                "特别行政区",
                "自治州",
                "地区",
                "市",
            ),
        )
        if short_region_name:
            _add_alias(
                region_aliases,
                alias=short_region_name,
                code=region_code,
            )

        _add_alias(
            region_aliases,
            alias=province_name,
            code=region_code,
        )

        short_province_name = _strip_controlled_suffix(
            province_name,
            (
                "壮族自治区",
                "回族自治区",
                "维吾尔自治区",
                "自治区",
                "特别行政区",
                "省",
                "市",
            ),
        )
        if short_province_name:
            _add_alias(
                region_aliases,
                alias=short_province_name,
                code=region_code,
            )

    for channel in fixed_dimensions["channels"]:
        channel_code = channel["channel_code"].strip()
        channel_name = channel["channel_name"].strip()

        _add_alias(
            channel_aliases,
            alias=channel_code,
            code=channel_code,
        )
        _add_alias(
            channel_aliases,
            alias=channel_name,
            code=channel_code,
        )

        short_channel_name = _strip_controlled_suffix(
            channel_name,
            (
                "官方商城",
                "旗舰店",
                "商城",
                "小程序",
            ),
        )
        if short_channel_name:
            _add_alias(
                channel_aliases,
                alias=short_channel_name,
                code=channel_code,
            )

    return (
        {
            alias: frozenset(codes)
            for alias, codes in region_aliases.items()
        },
        {
            alias: frozenset(codes)
            for alias, codes in channel_aliases.items()
        },
    )


def _match_aliases(
    *,
    normalized_question: str,
    aliases: dict[str, frozenset[str]],
) -> tuple[
    frozenset[str],
    tuple[str, ...],
]:
    matched_codes: set[str] = set()
    matched_terms: list[str] = []

    for alias in sorted(
        aliases,
        key=len,
        reverse=True,
    ):
        if alias not in normalized_question:
            continue

        matched_terms.append(alias)
        matched_codes.update(aliases[alias])

    return (
        frozenset(matched_codes),
        tuple(matched_terms),
    )


_GENERIC_REGION_SCOPE_PATTERNS = (
    r"(?:各|按|分|每个|不同|全部|所有)(?:地区|区域)",
    r"(?:哪个|哪一个)(?:地区|区域)",
    r"(?:地区|区域)(?:是)?(?:哪个|哪一个)",
)

_GENERIC_CHANNEL_SCOPE_PATTERNS = (
    r"(?:各|按|分|每个|不同|全部|所有)(?:渠道|平台)",
    r"(?:哪个|哪一个)(?:渠道|平台)",
    r"(?:渠道|平台)(?:是)?(?:哪个|哪一个)",
)

_SCOPE_BUSINESS_TOKEN = (
    r"(?:gmv|成交额|销售额|销售|成交|订单|单量|"
    r"退款|退款率|毛利|roi|客单价|表现|数据|多少)"
)


def _has_generic_scope_phrase(
    text: str,
    patterns: tuple[str, ...],
) -> bool:
    return any(
        re.search(pattern, text)
        for pattern in patterns
    )


def _has_explicit_region_intent(
    text: str,
) -> bool:
    if _has_generic_scope_phrase(
        text,
        _GENERIC_REGION_SCOPE_PATTERNS,
    ):
        return False

    return bool(
        re.search(
            (
                r"[\u4e00-\u9fffA-Za-z_]{1,12}"
                r"(?:地区|区域)"
                r"(?:的|上|中|内)?"
                + _SCOPE_BUSINESS_TOKEN
            ),
            text,
        )
    )


def _has_explicit_channel_intent(
    text: str,
) -> bool:
    if _has_generic_scope_phrase(
        text,
        _GENERIC_CHANNEL_SCOPE_PATTERNS,
    ):
        return False

    return bool(
        re.search(
            (
                r"[\u4e00-\u9fffA-Za-z_]{1,12}"
                r"(?:渠道|平台)"
                r"(?:的|上|中|内)?"
                + _SCOPE_BUSINESS_TOKEN
            ),
            text,
        )
    )


def resolve_requested_scope_v2(
    question: str,
) -> RequestedScopeResolutionV2:
    normalized_question = _normalize_text(question)

    (
        region_aliases,
        channel_aliases,
    ) = _build_scope_alias_catalog_v2()

    (
        region_codes,
        matched_region_terms,
    ) = _match_aliases(
        normalized_question=normalized_question,
        aliases=region_aliases,
    )

    (
        channel_codes,
        matched_channel_terms,
    ) = _match_aliases(
        normalized_question=normalized_question,
        aliases=channel_aliases,
    )

    unresolved_dimensions: set[
        RequestedScopeDimensionV2
    ] = set()

    if (
        not region_codes
        and _has_explicit_region_intent(
            normalized_question
        )
    ):
        unresolved_dimensions.add(
            RequestedScopeDimensionV2.REGION
        )

    if (
        not channel_codes
        and _has_explicit_channel_intent(
            normalized_question
        )
    ):
        unresolved_dimensions.add(
            RequestedScopeDimensionV2.CHANNEL
        )

    if unresolved_dimensions:
        return RequestedScopeResolutionV2(
            status=(
                RequestedScopeResolutionStatusV2
                .UNRESOLVED_EXPLICIT_SCOPE
            ),
            region_codes=region_codes,
            channel_codes=channel_codes,
            matched_region_terms=matched_region_terms,
            matched_channel_terms=matched_channel_terms,
            unresolved_dimensions=frozenset(
                unresolved_dimensions
            ),
        )

    if not region_codes and not channel_codes:
        return RequestedScopeResolutionV2(
            status=(
                RequestedScopeResolutionStatusV2
                .NO_EXPLICIT_SCOPE
            ),
        )

    return RequestedScopeResolutionV2(
        status=RequestedScopeResolutionStatusV2.RESOLVED,
        region_codes=region_codes,
        channel_codes=channel_codes,
        matched_region_terms=matched_region_terms,
        matched_channel_terms=matched_channel_terms,
    )

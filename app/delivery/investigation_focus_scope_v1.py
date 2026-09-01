from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.delivery.contribution_investigation_recommendation_v1 import (
    ContributionInvestigationRecommendationV1,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionStatusV2,
    RequestedScopeResolutionV2,
    resolve_requested_scope_v2,
)


class InvestigationFocusDimensionV1(str, Enum):
    """Day93 第一版 Investigation Focus 只正式支持渠道焦点。"""

    CHANNEL = "channel"


class InvestigationFocusScopeV1(BaseModel):
    """
    从可信业务证据中提升出来的“继续调查焦点”。

    它与用户原始 Requested Scope 分离：
    - Requested Scope：用户最初明确要求查询的范围；
    - Investigation Focus：后续调查根据受治理 Evidence 推荐并经用户继续动作确认的焦点。

    当前 V1 只支持 Channel Focus，不把普通文本或 LLM 输出直接当成代码范围。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    dimension: InvestigationFocusDimensionV1
    member_key: str
    member_label: str
    channel_codes: frozenset[str]
    source_evidence_id: str

    # F02 Comparison Recommendation 已经包含该渠道两期可信值。
    # 为避免后续 Focused Change Breakdown 回到 UI 文本或重新猜值，
    # V1 允许把这组三个 server-trusted 数值随 Focus 一起继承。
    #
    # 兼容边界：
    # - 旧调用可全部为 None；
    # - 一旦提供任意一个，就必须三者齐全且 delta 可对账。
    reference_value: Decimal | None = None
    current_value: Decimal | None = None
    delta: Decimal | None = None

    @model_validator(mode="after")
    def validate_focus(self) -> "InvestigationFocusScopeV1":
        if self.dimension != InvestigationFocusDimensionV1.CHANNEL:
            raise ValueError("Investigation Focus V1 只支持 Channel。")

        if not self.member_key.strip():
            raise ValueError("member_key 不能为空。")

        if not self.member_label.strip():
            raise ValueError("member_label 不能为空。")

        if len(self.channel_codes) != 1:
            raise ValueError(
                "Channel Investigation Focus 必须确定性绑定恰好一个 channel_code。"
            )

        if not self.source_evidence_id.strip():
            raise ValueError("source_evidence_id 不能为空。")

        comparison_values = (
            self.reference_value,
            self.current_value,
            self.delta,
        )

        provided_count = sum(
            value is not None
            for value in comparison_values
        )

        if provided_count not in {0, 3}:
            raise ValueError(
                "Investigation Focus 的 reference/current/delta "
                "必须全部提供或全部省略。"
            )

        if provided_count == 3:
            assert self.reference_value is not None
            assert self.current_value is not None
            assert self.delta is not None

            expected_delta = (
                self.current_value
                - self.reference_value
            )

            if expected_delta != self.delta:
                raise ValueError(
                    "Investigation Focus 的 delta "
                    "必须等于 current_value - reference_value。"
                )

        return self


def _resolve_single_channel_code_v1(
    *,
    member_key: str,
    member_label: str,
) -> frozenset[str]:
    """
    用现有 server-owned alias catalog 把已释放渠道名称重新绑定到代码。

    这一步不让 LLM 猜，也不从 UI 自由文本构造 code。
    member_key / member_label 都来自 Protected Contribution Evidence；
    两者若都能解析，结果必须一致，否则 fail closed。
    """

    resolved_codes: list[frozenset[str]] = []

    for token in dict.fromkeys(
        (
            member_key.strip(),
            member_label.strip(),
        )
    ):
        if not token:
            continue

        resolved = resolve_requested_scope_v2(token)

        if (
            resolved.status
            == RequestedScopeResolutionStatusV2.RESOLVED
            and len(resolved.channel_codes) == 1
            and not resolved.region_codes
            and not resolved.unresolved_dimensions
        ):
            resolved_codes.append(resolved.channel_codes)

    if not resolved_codes:
        raise ValueError(
            "可信 Contribution 渠道名称无法绑定到唯一 server-owned channel_code。"
        )

    first = resolved_codes[0]

    if any(item != first for item in resolved_codes[1:]):
        raise ValueError(
            "member_key / member_label 对应的渠道代码不一致；不能建立 Investigation Focus。"
        )

    return first


def build_contribution_investigation_focus_scope_v1(
    recommendation: ContributionInvestigationRecommendationV1,
) -> InvestigationFocusScopeV1:
    """
    把 F02 已完成 Reconciliation 的渠道调查建议提升为结构化 Focus。

    这里只允许 GMV × Channel Recommendation；
    recommendation 自身已经保证它不是因果结论。
    """

    if recommendation.metric_name != "gmv":
        raise ValueError("F02 Investigation Focus 只接受 GMV Recommendation。")

    if recommendation.dimension_name != "channel":
        raise ValueError("F02 Investigation Focus 只接受 Channel Recommendation。")

    channel_codes = _resolve_single_channel_code_v1(
        member_key=recommendation.member_key,
        member_label=recommendation.member_label,
    )

    return InvestigationFocusScopeV1(
        dimension=InvestigationFocusDimensionV1.CHANNEL,
        member_key=recommendation.member_key,
        member_label=recommendation.member_label,
        channel_codes=channel_codes,
        source_evidence_id=recommendation.contribution_evidence_id,
        reference_value=recommendation.reference_value,
        current_value=recommendation.current_value,
        delta=recommendation.delta,
    )


def merge_requested_scope_with_investigation_focus_v1(
    *,
    requested_scope: RequestedScopeResolutionV2 | None,
    investigation_focus: InvestigationFocusScopeV1 | None,
) -> RequestedScopeResolutionV2 | None:
    """
    生成 Governed Planning 实际使用的 Investigation Effective Scope。

    语义：
      Authorized Scope ∩ Requested Scope ∩ Investigation Focus

    AccessContext 的 Authorized Scope 仍由 Governance 层负责；
    本函数只把 Requested Scope 与可信 Focus 合并为下一轮 Row Scope 请求。
    """

    if investigation_focus is None:
        return requested_scope

    if (
        requested_scope is not None
        and requested_scope.status
        == RequestedScopeResolutionStatusV2.UNRESOLVED_EXPLICIT_SCOPE
    ):
        raise ValueError(
            "未解决的 Requested Scope 不能与 Investigation Focus 合并。"
        )

    requested_regions = (
        requested_scope.region_codes
        if requested_scope is not None
        else frozenset()
    )
    requested_channels = (
        requested_scope.channel_codes
        if requested_scope is not None
        else frozenset()
    )

    focus_channels = investigation_focus.channel_codes

    if requested_channels:
        channel_codes = requested_channels & focus_channels
        if not channel_codes:
            raise ValueError(
                "Requested Channel 与 Investigation Focus Channel 不相交；"
                "不能扩大或偷换调查范围。"
            )
    else:
        channel_codes = focus_channels

    matched_region_terms = (
        requested_scope.matched_region_terms
        if requested_scope is not None
        else ()
    )
    existing_channel_terms = (
        requested_scope.matched_channel_terms
        if requested_scope is not None
        else ()
    )

    matched_channel_terms = tuple(
        dict.fromkeys(
            (
                *existing_channel_terms,
                investigation_focus.member_label,
            )
        )
    )

    return RequestedScopeResolutionV2(
        status=RequestedScopeResolutionStatusV2.RESOLVED,
        region_codes=requested_regions,
        channel_codes=channel_codes,
        matched_region_terms=matched_region_terms,
        matched_channel_terms=matched_channel_terms,
        unresolved_dimensions=frozenset(),
    )

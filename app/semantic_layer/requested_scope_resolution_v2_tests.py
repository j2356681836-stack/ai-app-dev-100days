from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeDimensionV2,
    RequestedScopeResolutionStatusV2,
    resolve_requested_scope_v2,
)


def check(
    name: str,
    condition: bool,
) -> None:
    if not condition:
        raise AssertionError(
            f"FAILED: {name}"
        )
    print(f"PASS: {name}")


def main() -> None:
    shanghai = resolve_requested_scope_v2(
        "2025年上海地区GMV是多少？"
    )
    check(
        "上海简称解析为 SHANGHAI",
        (
            shanghai.status
            == RequestedScopeResolutionStatusV2.RESOLVED
            and shanghai.region_codes
            == frozenset({"SHANGHAI"})
        ),
    )

    tmall = resolve_requested_scope_v2(
        "2025年天猫GMV是多少？"
    )
    check(
        "天猫简称解析为 TMALL",
        (
            tmall.status
            == RequestedScopeResolutionStatusV2.RESOLVED
            and tmall.channel_codes
            == frozenset({"TMALL"})
        ),
    )

    combined = resolve_requested_scope_v2(
        "2025年上海地区天猫GMV是多少？"
    )
    check(
        "Region 与 Channel 可同时解析",
        (
            combined.region_codes
            == frozenset({"SHANGHAI"})
            and combined.channel_codes
            == frozenset({"TMALL"})
        ),
    )

    no_scope = resolve_requested_scope_v2(
        "2025年GMV是多少？"
    )
    check(
        "无显式维度值保持 NO_EXPLICIT_SCOPE",
        (
            no_scope.status
            == RequestedScopeResolutionStatusV2
            .NO_EXPLICIT_SCOPE
        ),
    )

    grain_only = resolve_requested_scope_v2(
        "2025年各渠道GMV是多少？"
    )
    check(
        "各渠道是 Grain，不伪造成具体 Scope",
        (
            grain_only.status
            == RequestedScopeResolutionStatusV2
            .NO_EXPLICIT_SCOPE
        ),
    )

    unknown_region = resolve_requested_scope_v2(
        "2025年火星地区GMV是多少？"
    )
    check(
        "未知显式 Region 不得退化为 NO_EXPLICIT_SCOPE",
        (
            unknown_region.status
            == RequestedScopeResolutionStatusV2
            .UNRESOLVED_EXPLICIT_SCOPE
            and unknown_region.unresolved_dimensions
            == frozenset(
                {
                    RequestedScopeDimensionV2.REGION,
                }
            )
        ),
    )

    unknown_channel = resolve_requested_scope_v2(
        "2025年火星渠道GMV是多少？"
    )
    check(
        "未知显式 Channel 不得退化为 NO_EXPLICIT_SCOPE",
        (
            unknown_channel.status
            == RequestedScopeResolutionStatusV2
            .UNRESOLVED_EXPLICIT_SCOPE
            and unknown_channel.unresolved_dimensions
            == frozenset(
                {
                    RequestedScopeDimensionV2.CHANNEL,
                }
            )
        ),
    )

    ambiguous_best = resolve_requested_scope_v2(
        "2025年表现最好的渠道是哪一个？"
    )
    check(
        "表现最好的渠道不是未知具体 Channel",
        (
            ambiguous_best.status
            == RequestedScopeResolutionStatusV2
            .NO_EXPLICIT_SCOPE
        ),
    )

    best_channel_prefix = resolve_requested_scope_v2(
        "2025年哪一个渠道表现最好？"
    )
    check(
        "哪一个渠道表现最好是 Grain/Ranking，不是未知具体 Channel",
        (
            best_channel_prefix.status
            == RequestedScopeResolutionStatusV2
            .NO_EXPLICIT_SCOPE
        ),
    )

    best_channel_metric = resolve_requested_scope_v2(
        "2025年哪个渠道GMV最高？"
    )
    check(
        "哪个渠道GMV最高不是未知具体 Channel",
        (
            best_channel_metric.status
            == RequestedScopeResolutionStatusV2
            .NO_EXPLICIT_SCOPE
        ),
    )

    best_channel_refund = resolve_requested_scope_v2(
        "2025年哪个渠道退款率最高？"
    )
    check(
        "哪个渠道退款率最高不是未知具体 Channel",
        (
            best_channel_refund.status
            == RequestedScopeResolutionStatusV2
            .NO_EXPLICIT_SCOPE
        ),
    )

    best_region_prefix = resolve_requested_scope_v2(
        "2025年哪一个地区表现最好？"
    )
    check(
        "哪一个地区表现最好是 Grain/Ranking，不是未知具体 Region",
        (
            best_region_prefix.status
            == RequestedScopeResolutionStatusV2
            .NO_EXPLICIT_SCOPE
        ),
    )

    best_region_metric = resolve_requested_scope_v2(
        "2025年哪个地区GMV最高？"
    )
    check(
        "哪个地区GMV最高不是未知具体 Region",
        (
            best_region_metric.status
            == RequestedScopeResolutionStatusV2
            .NO_EXPLICIT_SCOPE
        ),
    )

    reversed_channel_question = resolve_requested_scope_v2(
        "2025年表现最好的渠道是哪一个？"
    )
    check(
        "渠道是哪一个仍保持 Grain/Ranking 语义",
        (
            reversed_channel_question.status
            == RequestedScopeResolutionStatusV2
            .NO_EXPLICIT_SCOPE
        ),
    )

    # 安全边界不能因为增加疑问词规则而放松。
    still_unknown_channel = resolve_requested_scope_v2(
        "2025年火星渠道表现怎么样？"
    )
    check(
        "未知具体 Channel 仍保持 fail-closed",
        (
            still_unknown_channel.status
            == RequestedScopeResolutionStatusV2
            .UNRESOLVED_EXPLICIT_SCOPE
            and still_unknown_channel.unresolved_dimensions
            == frozenset(
                {RequestedScopeDimensionV2.CHANNEL}
            )
        ),
    )

    still_unknown_region = resolve_requested_scope_v2(
        "2025年火星地区表现怎么样？"
    )
    check(
        "未知具体 Region 仍保持 fail-closed",
        (
            still_unknown_region.status
            == RequestedScopeResolutionStatusV2
            .UNRESOLVED_EXPLICIT_SCOPE
            and still_unknown_region.unresolved_dimensions
            == frozenset(
                {RequestedScopeDimensionV2.REGION}
            )
        ),
    )

    print("=" * 72)
    print("Requested Scope Resolution V2 tests passed.")


if __name__ == "__main__":
    main()

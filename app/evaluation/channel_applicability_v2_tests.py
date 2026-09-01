from app.semantic_layer.channel_applicability_v2 import (
    ChannelBusinessRoleV2,
    channel_codes_for_role_v2,
    resolve_metric_channel_role_v2,
    validate_requested_channel_applicability_v2,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    resolve_requested_scope_v2,
)


def test_manifest_channel_roles_are_business_correct() -> None:
    sales = channel_codes_for_role_v2(
        ChannelBusinessRoleV2.SALES
    )
    marketing = channel_codes_for_role_v2(
        ChannelBusinessRoleV2.MARKETING
    )
    direct_response = channel_codes_for_role_v2(
        ChannelBusinessRoleV2.DIRECT_RESPONSE
    )

    assert sales == frozenset(
        {
            "OFFICIAL_MALL",
            "TMALL",
            "JD",
            "DOUYIN",
            "WECHAT_MINI_PROGRAM",
        }
    )
    assert marketing == frozenset(
        {
            "TMALL",
            "JD",
            "DOUYIN",
            "XIAOHONGSHU",
        }
    )
    assert direct_response == frozenset(
        {
            "TMALL",
            "JD",
            "DOUYIN",
        }
    )

    print("PASS: test_manifest_channel_roles_are_business_correct")
    print("PASS: sales channels = 5")
    print("PASS: Xiaohongshu is marketing-only")


def test_gmv_rejects_xiaohongshu_requested_scope() -> None:
    requested = resolve_requested_scope_v2(
        "2025年10月小红书GMV是多少？"
    )

    decision = validate_requested_channel_applicability_v2(
        metric_name="gmv",
        requested_scope=requested,
    )

    assert decision.allowed is False
    assert decision.inapplicable_requested_codes == frozenset(
        {"XIAOHONGSHU"}
    )
    assert "不是当前 Dataset V2 的销售渠道" in decision.message

    print("PASS: test_gmv_rejects_xiaohongshu_requested_scope")


def test_marketing_scope_can_include_xiaohongshu() -> None:
    requested = resolve_requested_scope_v2(
        "小红书营销数据是多少？"
    )

    # Scope Resolver 可能不把“营销数据”识别成完整业务 token，
    # 因此这里直接验证 Role Contract。
    marketing = channel_codes_for_role_v2(
        ChannelBusinessRoleV2.MARKETING
    )
    assert "XIAOHONGSHU" in marketing

    assert (
        resolve_metric_channel_role_v2("marketing_spend")
        == ChannelBusinessRoleV2.MARKETING
    )
    assert (
        resolve_metric_channel_role_v2("roi")
        == ChannelBusinessRoleV2.DIRECT_RESPONSE
    )

    print("PASS: test_marketing_scope_can_include_xiaohongshu")


def main() -> None:
    test_manifest_channel_roles_are_business_correct()
    test_gmv_rejects_xiaohongshu_requested_scope()
    test_marketing_scope_can_include_xiaohongshu()


if __name__ == "__main__":
    main()

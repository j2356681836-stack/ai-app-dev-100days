from app.delivery.decision_console_runtime_v2 import (
    build_day89_local_access_context_v2,
)
from app.semantic_layer.channel_applicability_v2 import (
    ChannelBusinessRoleV2,
)


def test_default_decision_console_context_is_sales_scope() -> None:
    context = build_day89_local_access_context_v2(
        request_id="test-sales-scope"
    )

    assert context.allowed_channel_codes == frozenset(
        {
            "OFFICIAL_MALL",
            "TMALL",
            "JD",
            "DOUYIN",
            "WECHAT_MINI_PROGRAM",
        }
    )
    assert "XIAOHONGSHU" not in context.allowed_channel_codes

    print(
        "PASS: "
        "test_default_decision_console_context_is_sales_scope"
    )


def test_marketing_context_explicitly_includes_xiaohongshu() -> None:
    context = build_day89_local_access_context_v2(
        request_id="test-marketing-scope",
        channel_role=ChannelBusinessRoleV2.MARKETING,
    )

    assert context.allowed_channel_codes == frozenset(
        {
            "TMALL",
            "JD",
            "DOUYIN",
            "XIAOHONGSHU",
        }
    )

    print(
        "PASS: "
        "test_marketing_context_explicitly_includes_xiaohongshu"
    )


def main() -> None:
    test_default_decision_console_context_is_sales_scope()
    test_marketing_context_explicitly_includes_xiaohongshu()


if __name__ == "__main__":
    main()

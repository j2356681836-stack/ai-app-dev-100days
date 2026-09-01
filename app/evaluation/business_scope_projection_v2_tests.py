from app.delivery.business_scope_projection_v2 import (
    build_business_scope_projection_v2,
)
from app.semantic_layer.channel_applicability_v2 import (
    ChannelBusinessRoleV2,
)


FULL_AUTHORIZED_SCOPE = (
    "地区代码：BEIJING、CHONGQING、GUANGDONG_GUANGZHOU、"
    "GUANGDONG_SHENZHEN、GUANGXI_GUILIN、HENAN_LUOYANG、"
    "HUBEI_WUHAN、JIANGSU_NANJING、LIAONING_SHENYANG、"
    "SHAANXI_XIAN、SHANDONG_QINGDAO、SHANGHAI、"
    "SICHUAN_CHENGDU、SICHUAN_MIANYANG、ZHEJIANG_HANGZHOU、"
    "ZHEJIANG_JINHUA；渠道代码：DOUYIN、JD、OFFICIAL_MALL、"
    "TMALL、WECHAT_MINI_PROGRAM、XIAOHONGSHU"
)


def test_gmv_business_scope_filters_marketing_only_channel() -> None:
    projection = build_business_scope_projection_v2(
        FULL_AUTHORIZED_SCOPE
    )

    assert projection.channel_summary == "全部销售渠道（5个）"
    assert "小红书" not in projection.channel_member_labels
    assert "京东旗舰店" in projection.channel_member_labels
    assert projection.geography_summary == "全部可用城市（16个）"

    print(
        "PASS: "
        "test_gmv_business_scope_filters_marketing_only_channel"
    )
    print("PASS: GMV scope = 全部销售渠道（5个）")
    print("PASS: Xiaohongshu hidden from GMV business scope")


def test_marketing_projection_can_show_xiaohongshu() -> None:
    projection = build_business_scope_projection_v2(
        FULL_AUTHORIZED_SCOPE,
        channel_role=ChannelBusinessRoleV2.MARKETING,
    )

    assert projection.channel_summary == "全部营销渠道（4个）"
    assert "小红书" in projection.channel_member_labels
    assert "品牌官方商城" not in projection.channel_member_labels

    print("PASS: test_marketing_projection_can_show_xiaohongshu")


def main() -> None:
    test_gmv_business_scope_filters_marketing_only_channel()
    test_marketing_projection_can_show_xiaohongshu()


if __name__ == "__main__":
    main()

from app.agents.geography_hierarchy_v2 import (
    AREA_DISPLAY_LABELS_V2,
    build_geography_focus_scope_v2,
    get_geography_member_v2,
    list_geography_members_v2,
    merge_requested_scope_with_geography_focus_v2,
    next_geography_level_v2,
)
from app.agents.investigation_route_v2 import GeographyLevelV2
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionStatusV2,
    resolve_requested_scope_v2,
)


def test_geography_levels_are_strictly_ordered() -> None:
    assert next_geography_level_v2(None) == GeographyLevelV2.AREA
    assert (
        next_geography_level_v2(GeographyLevelV2.AREA)
        == GeographyLevelV2.PROVINCE
    )
    assert (
        next_geography_level_v2(GeographyLevelV2.PROVINCE)
        == GeographyLevelV2.CITY
    )
    assert next_geography_level_v2(GeographyLevelV2.CITY) is None

    print("PASS: test_geography_levels_are_strictly_ordered")


def test_area_catalog_has_seven_business_regions() -> None:
    areas = list_geography_members_v2(
        level=GeographyLevelV2.AREA
    )

    assert len(areas) == 7
    assert set(AREA_DISPLAY_LABELS_V2) == {
        item.member_key
        for item in areas
    }

    south = next(
        item
        for item in areas
        if item.member_key == "south"
    )

    assert south.member_label == "华南"
    assert south.region_codes == frozenset(
        {
            "GUANGDONG_GUANGZHOU",
            "GUANGDONG_SHENZHEN",
            "GUANGXI_GUILIN",
        }
    )

    print("PASS: test_area_catalog_has_seven_business_regions")
    print("PASS: south = 华南")
    print("PASS: 华南 binds to 3 real city region_codes")


def test_area_to_province_to_city_is_manifest_backed() -> None:
    south = get_geography_member_v2(
        level=GeographyLevelV2.AREA,
        member_key="south",
    )

    provinces = list_geography_members_v2(
        level=GeographyLevelV2.PROVINCE,
        parent=south,
    )

    assert {
        item.member_label
        for item in provinces
    } == {
        "广东省",
        "广西壮族自治区",
    }

    guangdong = next(
        item
        for item in provinces
        if item.member_label == "广东省"
    )

    cities = list_geography_members_v2(
        level=GeographyLevelV2.CITY,
        parent=guangdong,
    )

    assert {
        item.member_label
        for item in cities
    } == {
        "广州市",
        "深圳市",
    }

    print("PASS: test_area_to_province_to_city_is_manifest_backed")


def test_geography_focus_narrows_to_region_codes() -> None:
    south = get_geography_member_v2(
        level=GeographyLevelV2.AREA,
        member_key="south",
    )
    focus = build_geography_focus_scope_v2(
        member=south,
        source_evidence_id="ev-area-south",
    )

    effective = merge_requested_scope_with_geography_focus_v2(
        requested_scope=None,
        geography_focus=focus,
    )

    assert effective is not None
    assert (
        effective.status
        == RequestedScopeResolutionStatusV2.RESOLVED
    )
    assert effective.region_codes == south.region_codes

    print("PASS: test_geography_focus_narrows_to_region_codes")


def test_geography_focus_cannot_escape_original_requested_scope() -> None:
    requested = resolve_requested_scope_v2(
        "上海GMV怎么样？"
    )

    south = get_geography_member_v2(
        level=GeographyLevelV2.AREA,
        member_key="south",
    )
    focus = build_geography_focus_scope_v2(
        member=south,
        source_evidence_id="ev-area-south",
    )

    try:
        merge_requested_scope_with_geography_focus_v2(
            requested_scope=requested,
            geography_focus=focus,
        )
    except ValueError as exc:
        assert "不相交" in str(exc)
        print(
            "PASS: "
            "test_geography_focus_cannot_escape_original_requested_scope"
        )
        return

    raise AssertionError(
        "Geography Focus must not widen beyond original Requested Scope."
    )


def main() -> None:
    test_geography_levels_are_strictly_ordered()
    test_area_catalog_has_seven_business_regions()
    test_area_to_province_to_city_is_manifest_backed()
    test_geography_focus_narrows_to_region_codes()
    test_geography_focus_cannot_escape_original_requested_scope()


if __name__ == "__main__":
    main()

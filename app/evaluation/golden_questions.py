GOLDEN_QUESTIONS = [
    {
        "id": "case_001",
        "question": "哪个品类的退款率最高？",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "fact_refunds",
            "dim_product",
        ],
        "expected_columns": [
            "category",
            "refund_rate_pct",
        ],
        "should_execute": True,
    },
    {
        "id": "case_002",
        "question": "哪个品类销售额最高？",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "dim_product",
        ],
        "expected_columns": [
            "category",
        ],
        "should_execute": True,
    },
    {
        "id": "case_003",
        "question": "退款率最高的是啥？",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "fact_refunds",
            "dim_product",
        ],
        "expected_columns": [
            "category",
        ],
        "should_execute": True,
    },
    {
        "id": "case_005",
        "question": "卖得最好的是哪个品类？",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "dim_product",
        ],
        "expected_columns": [
            "category",
        ],
        "should_execute": True,
    },
    {
        "id": "case_006",
        "question": "退款率前三的品类",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "dim_product",
            "fact_refunds",
        ],
        "expected_columns": [
            "category",
        ],
        "should_execute": True,
    },
    {
        "id": "case_008",
        "question": "哪个品类退货最严重？",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "dim_product",
            "fact_refunds",
        ],
        "expected_columns": [
            "category",
        ],
        "should_execute": True,
    },
    {
        "id": "case_010",
        "question": "销售额Top5品类",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "dim_product",
        ],
        "expected_columns": [
            "category",
        ],
        "should_execute": True,
    },
    {
        "id": "case_013",
        "question": "哪个品类退得最厉害",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "dim_product",
            "fact_refunds",
        ],
        "expected_columns": [
            "category",
        ],
        "should_execute": True,
    },
    {
        "id": "case_014",
        "question": "哪个品类订单最多",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "dim_product",
        ],
        "expected_columns": [
            "category",
            "order_count"
        ],
        "should_execute": True,
    },
    {
        "id": "case_015",
        "question": "哪个品类销量最高",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "dim_product",
        ],
        "expected_columns": [
            "category",
            "sales_quantity"
        ],
        "should_execute": True,
    },
    {
        "id": "case_016",
        "question": "哪个品类成交最多",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "dim_product",
        ],
        "expected_columns": [
            "category",
            "order_count",
        ],
        "should_execute": True,
    },
    {
        "id": "case_017",
        "question": "哪个品类卖出最多件",
        "expected_tables": [
            "fact_order_items",
            "fact_orders",
            "dim_product",
        ],
        "expected_columns": [
            "category",
            "sales_quantity",
        ],
        "should_execute": True,
    },
    {
        "id": "case_018",
        "question": "哪个渠道销售额最高",
        "expected_tables": [
            "fact_orders",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "channel_sales_amount",
        ],
        "expected_result": {
            "channel_name": "天猫",
            "channel_sales_amount": 2445170.92,
        },
        "expected_generation_method": "llm",
        "should_execute": True,
    },
    {
        "id": "case_019",
        "question": "各渠道销售额排名",
        "expected_tables": [
            "fact_orders",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "channel_sales_amount",
        ],
        "expected_order": {
            "field": "channel_name",
            "values": [
                "天猫",
                "抖音",
                "京东",
                "小红书",
                "微信小程序",
            ],
        },
        "expected_generation_method": "llm",
        "should_execute": True,
    },
    {
        "id": "case_020",
        "question": "哪个渠道退款率最高",
        "expected_tables": [
            "fact_orders",
            "fact_order_items",
            "fact_refunds",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "channel_refund_rate_pct",
        ],
        "expected_result": {
            "channel_name": "抖音",
            "channel_refund_rate_pct": 6.86,
        },
        "expected_generation_method": "llm",
        "should_execute": True,
    },
    {
        "id": "case_021",
        "question": "各渠道退款率排名",
        "expected_tables": [
            "fact_orders",
            "fact_order_items",
            "fact_refunds",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "channel_refund_rate_pct",
        ],
        "expected_order": {
            "field": "channel_name",
            "values": [
                "抖音",
                "天猫",
                "京东",
                "微信小程序",
                "小红书",
            ],
        },
        "expected_generation_method": "llm",
        "should_execute": True,
    },
        {
        "id": "case_022",
        "question": "哪个渠道ROI最高",
        "expected_tables": [
            "fact_orders",
            "fact_marketing_spend",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "roi",
        ],
        "expected_result": {
            "channel_name": "天猫",
            "roi": 1.68,
        },
        "expected_generation_method": "template",
        "expected_intent": {
            "limit": 1,
            "ranking_type": "top1",
            "sort_hint": "desc",
            "dimension": "channel",
            "final_sort_direction": "desc",
            "sort_field": "roi",
        },
        "should_execute": True,
    },
    {
        "id": "case_023",
        "question": "各渠道ROI排名",
        "expected_tables": [
            "fact_orders",
            "fact_marketing_spend",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "roi",
        ],
        "expected_order": {
            "field": "channel_name",
            "values": [
                "天猫",
                "微信小程序",
                "京东",
                "抖音",
                "小红书",
            ],
        },
        "expected_generation_method": "template",
        "expected_intent": {
            "limit": None,
            "ranking_type": "ranking",
            "sort_hint": None,
            "dimension": "channel",
            "final_sort_direction": "desc",
            "sort_field": "roi",
        },
        "should_execute": True,
    },
        {
        "id": "case_024",
        "question": "哪个渠道获客成本最低",
        "expected_tables": [
            "fact_orders",
            "fact_marketing_spend",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "cac",
        ],
        "expected_result": {
            "channel_name": "天猫",
            "cac": 2284.40,
        },
        "expected_generation_method": "template",
        "expected_intent": {
            "limit": 1,
            "ranking_type": "top1",
            "sort_hint": "asc",
            "dimension": "channel",
            "final_sort_direction": "asc",
            "sort_field": "cac",
        },
        "should_execute": True,
    },
    {
        "id": "case_025",
        "question": "各渠道获客成本排名",
        "expected_tables": [
            "fact_orders",
            "fact_marketing_spend",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "cac",
        ],
        "expected_order": {
            "field": "channel_name",
            "values": [
                "天猫",
                "微信小程序",
                "京东",
                "抖音",
                "小红书",
            ],
        },
        "expected_generation_method": "template",
        "expected_intent": {
            "limit": None,
            "ranking_type": "ranking",
            "sort_hint": None,
            "dimension": "channel",
            "final_sort_direction": "asc",
            "sort_field": "cac",
        },
        "should_execute": True,
    },
    {
        "id": "case_026",
        "question": "渠道ROI从低到高排名",
        "expected_tables": [
            "fact_orders",
            "fact_marketing_spend",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "roi",
        ],
        "expected_generation_method": "template",
        "expected_intent": {
            "limit": None,
            "ranking_type": "ranking",
            "sort_hint": "asc",
            "dimension": "channel",
            "final_sort_direction": "asc",
            "sort_field": "roi",
        },
        "expected_order": {
            "field": "channel_name",
            "values": [
                "小红书",
                "抖音",
                "京东",
                "微信小程序",
                "天猫",
            ],
        },
    },
    {
        "id": "case_027",
        "question": "渠道销售额从低到高排名",
        "expected_tables": [
            "fact_orders",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "channel_sales_amount",
        ],
        "expected_generation_method": "llm",
        "expected_intent": {
            "limit": None,
            "ranking_type": "ranking",
            "sort_hint": "asc",
            "dimension": "channel",
            "final_sort_direction": "asc",
            "sort_field": None,
        },
        "expected_order": {
            "field": "channel_name",
            "values": [
                "微信小程序",
                "小红书",
                "京东",
                "抖音",
                "天猫",
            ],
        },
    },
    {
        "id": "case_028",
        "question": "渠道销售额Top3",
        "expected_tables": [
            "fact_orders",
            "dim_channel",
        ],
        "expected_columns": [
            "channel_name",
            "channel_sales_amount",
        ],
        "expected_generation_method": "llm",
        "expected_intent": {
            "limit": 3,
            "ranking_type": "topn",
            "sort_hint": None,
            "dimension": "channel",
            "final_sort_direction": None,
            "sort_field": None,
        },
        "expected_order": {
            "field": "channel_name",
            "values": [
                "天猫",
                "抖音",
                "京东",
            ],
        },
    }
]
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
]
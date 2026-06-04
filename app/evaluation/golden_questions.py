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
]
RETRIEVAL_EVAL_CASES = [
    {
        "case_id": "retrieval_case_001",
        "question": "最赚钱",
        "description": "模糊赚钱类问题，应进入 clarification，优先围绕销售额 / ROI 澄清，CAC 不应作为赚钱候选。",
        "expected_status": "needs_clarification",
        "expected_search_type_in": ["embedding"],
        "must_include_any_options": [
            "roi",
            "channel_sales_amount",
            "item_sales_amount",
            "order_paid_amount",
        ],
        "forbidden_options": [
            "cac",
        ],
    },
    {
        "case_id": "retrieval_case_002",
        "question": "哪个渠道最划算",
        "description": "渠道划算类问题，应优先围绕 ROI 澄清，CAC 可以作为候选，但不应排在 ROI 前。",
        "expected_status": "needs_clarification",
        "expected_search_type_in": ["embedding"],
        "expected_top_option": "roi",
        "must_include_options": [
            "roi",
            "cac",
        ],
        "forbidden_options": [
            "channel_refund_rate",
        ],
    },
    {
        "case_id": "retrieval_case_003",
        "question": "拉新效率最高",
        "description": "拉新效率问题应优先关联 CAC，不应混入退款率。",
        "expected_status": "needs_clarification",
        "expected_search_type_in": ["embedding"],
        "expected_top_option": "cac",
        "must_include_options": [
            "cac",
        ],
        "forbidden_options": [
            "refund_rate",
        ],
    },
    {
        "case_id": "retrieval_case_004",
        "question": "哪个品类订单最多",
        "description": "明确订单数问题，应由 rule layer 命中 order_count。",
        "expected_status": "matched",
        "expected_method": "rule",
        "expected_top_option": "order_count",
        "expected_search_type_in": ["alias", "keyword_group"],
    },
    {
        "case_id": "retrieval_case_005",
        "question": "哪个品类销量最高",
        "description": "明确销量问题，应由 rule layer 命中 sales_quantity。",
        "expected_status": "matched",
        "expected_method": "rule",
        "expected_top_option": "sales_quantity",
        "expected_search_type_in": ["alias", "keyword_group"],
    },
    {
        "case_id": "retrieval_case_006",
        "question": "销售额Top5品类",
        "description": "明确销售额 TopN 问题，应由 rule layer 命中 item_sales_amount。",
        "expected_status": "matched",
        "expected_method": "rule",
        "expected_top_option": "item_sales_amount",
        "expected_search_type_in": ["alias", "keyword_group"],
    },
]
ANSWER_EVAL_CASES = [
    {
        "id": "answer_case_001",
        "source_case_id": "case_018",
        "question": "哪个渠道销售额最高",
        "context": {
            "columns": [
                "channel_name",
                "channel_sales_amount",
            ],
            "rows": [
                {
                    "channel_name": "天猫",
                    "channel_sales_amount": 2445170.92,
                }
            ],
        },
        "answer": "渠道销售额排名第一的是：天猫 2445170.92。",
        "expected_answer_points": [
            "天猫",
            "2445170.92",
        ],
        "reference_answer": "渠道销售额最高的是天猫，销售额为 2445170.92。",
        "rubric": {
            "faithfulness": "回答中的渠道名称和销售额必须能从 context.rows 中找到，不能添加数据中不存在的原因。",
            "relevance": "回答必须直接说明哪个渠道销售额最高。",
            "completeness": "回答必须同时包含渠道名称和销售额。",
            "clarity": "回答需要让业务用户能直接理解。",
        },
    },
    {
        "id": "answer_case_002",
        "source_case_id": "case_029",
        "question": "品类退款率Top3",
        "context": {
            "columns": [
                "category",
                "refund_rate_pct",
            ],
            "rows": [
                {
                    "category": "精华",
                    "refund_rate_pct": 10.0,
                },
                {
                    "category": "防晒",
                    "refund_rate_pct": 4.55,
                },
                {
                    "category": "面膜",
                    "refund_rate_pct": 4.48,
                },
            ],
        },
        "answer": "品类退款率Top3分别是：精华 10.0%，防晒 4.55%，面膜 4.48%。",
        "expected_answer_points": [
            "精华",
            "10.0",
            "防晒",
            "4.55",
            "面膜",
            "4.48",
        ],
        "reference_answer": "品类退款率前三分别是精华 10.0%、防晒 4.55%、面膜 4.48%。",
        "rubric": {
            "faithfulness": "回答中的品类和退款率必须全部来自 context.rows，不能添加退款原因。",
            "relevance": "回答必须覆盖用户询问的 Top3 品类退款率。",
            "completeness": "回答必须包含三个品类及其退款率。",
            "clarity": "回答应按排名顺序清楚列出三个品类及退款率。",
        },
    },
    {
        "id": "answer_case_003",
        "source_case_id": "case_030",
        "question": "品类退款率从低到高排名",
        "context": {
            "columns": [
                "category",
                "refund_rate_pct",
            ],
            "rows": [
                {
                    "category": "面霜",
                    "refund_rate_pct": 4.37,
                },
                {
                    "category": "洁面",
                    "refund_rate_pct": 4.47,
                },
                {
                    "category": "面膜",
                    "refund_rate_pct": 4.48,
                },
                {
                    "category": "防晒",
                    "refund_rate_pct": 4.55,
                },
                {
                    "category": "精华",
                    "refund_rate_pct": 10.0,
                },
            ],
        },
        "answer": "品类退款率从低到高依次为：面霜 4.37%，洁面 4.47%，面膜 4.48%，防晒 4.55%，精华 10.0%。",
        "expected_answer_points": [
            "面霜",
            "4.37",
            "洁面",
            "4.47",
            "面膜",
            "4.48",
            "防晒",
            "4.55",
            "精华",
            "10.0",
        ],
        "reference_answer": "品类退款率从低到高依次为面霜 4.37%、洁面 4.47%、面膜 4.48%、防晒 4.55%、精华 10.0%。",
        "rubric": {
            "faithfulness": "回答中的品类、退款率和排序方向必须由 context.rows 支撑。",
            "relevance": "回答必须体现从低到高排名。",
            "completeness": "回答必须包含所有返回品类及其退款率。",
            "clarity": "回答应清楚表达升序排名。",
        },
    },
    {
        "id": "answer_case_004",
        "source_case_id": "case_023",
        "question": "各渠道ROI排名",
        "context": {
            "columns": [
                "channel_name",
                "roi",
            ],
            "rows": [
                {
                    "channel_name": "天猫",
                    "roi": 1.68,
                },
                {
                    "channel_name": "微信小程序",
                    "roi": 1.51,
                },
                {
                    "channel_name": "京东",
                    "roi": 1.44,
                },
                {
                    "channel_name": "抖音",
                    "roi": 1.12,
                },
                {
                    "channel_name": "小红书",
                    "roi": 0.84,
                },
            ],
        },
        "answer": "渠道ROI从高到低依次为：天猫 1.68，微信小程序 1.51，京东 1.44，抖音 1.12，小红书 0.84。",
        "expected_answer_points": [
            "天猫",
            "1.68",
            "微信小程序",
            "1.51",
            "京东",
            "1.44",
            "抖音",
            "1.12",
            "小红书",
            "0.84",
        ],
        "reference_answer": "各渠道 ROI 从高到低依次为天猫 1.68、微信小程序 1.51、京东 1.44、抖音 1.12、小红书 0.84。",
        "rubric": {
            "faithfulness": "回答中的渠道名称、ROI 数值和排序必须全部来自 context.rows。",
            "relevance": "回答必须直接给出各渠道 ROI 排名。",
            "completeness": "回答必须覆盖所有返回渠道及其 ROI。",
            "clarity": "回答应清楚表达从高到低的 ROI 排名。",
        },
    },
    {
        "id": "answer_case_005",
        "source_case_id": "case_026",
        "question": "渠道ROI从低到高排名",
        "context": {
            "columns": [
                "channel_name",
                "roi",
            ],
            "rows": [
                {
                    "channel_name": "小红书",
                    "roi": 0.84,
                },
                {
                    "channel_name": "抖音",
                    "roi": 1.12,
                },
                {
                    "channel_name": "京东",
                    "roi": 1.44,
                },
                {
                    "channel_name": "微信小程序",
                    "roi": 1.51,
                },
                {
                    "channel_name": "天猫",
                    "roi": 1.68,
                },
            ],
        },
        "answer": "渠道ROI从低到高依次为：小红书 0.84，抖音 1.12，京东 1.44，微信小程序 1.51，天猫 1.68。",
        "expected_answer_points": [
            "小红书",
            "0.84",
            "抖音",
            "1.12",
            "京东",
            "1.44",
            "微信小程序",
            "1.51",
            "天猫",
            "1.68",
        ],
        "reference_answer": "渠道 ROI 从低到高依次为小红书 0.84、抖音 1.12、京东 1.44、微信小程序 1.51、天猫 1.68。",
        "rubric": {
            "faithfulness": "回答中的渠道名称、ROI 数值和升序顺序必须全部来自 context.rows。",
            "relevance": "回答必须体现渠道 ROI 从低到高排名。",
            "completeness": "回答必须覆盖所有返回渠道及其 ROI。",
            "clarity": "回答应清楚表达从低到高的 ROI 排名。",
        },
    },
    {
        "id": "answer_case_006_bad",
        "source_case_id": "case_029",
        "question": "品类退款率Top3",
        "context": {
            "columns": [
                "category",
                "refund_rate_pct",
            ],
            "rows": [
                {
                    "category": "精华",
                    "refund_rate_pct": 10.0,
                },
                {
                    "category": "防晒",
                    "refund_rate_pct": 4.55,
                },
                {
                    "category": "面膜",
                    "refund_rate_pct": 4.48,
                },
            ],
        },
        "answer": "品类退款率Top3分别是：面霜 10.0%，洁面 4.55%，面膜 4.48%。",
        "expected_answer_points": [
            "精华",
            "10.0",
            "防晒",
            "4.55",
            "面膜",
            "4.48",
        ],
        "reference_answer": "品类退款率前三分别是精华 10.0%、防晒 4.55%、面膜 4.48%。",
        "expected_judge_passed": False,
        "rubric": {
            "faithfulness": "回答中的品类和退款率必须全部来自 context.rows，不能添加退款原因。",
            "relevance": "回答必须覆盖用户询问的 Top3 品类退款率。",
            "completeness": "回答必须包含三个品类及其退款率。",
            "clarity": "回答应按排名顺序清楚列出三个品类及退款率。",
        },
    },
]


if __name__ == "__main__":
    print(f"Answer eval cases: {len(ANSWER_EVAL_CASES)}")

    for case in ANSWER_EVAL_CASES:
        print(case["id"], "-", case["question"])
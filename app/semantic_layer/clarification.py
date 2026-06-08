def build_clarification(result: dict) -> dict:
    """
    将 embedding 检索结果转换为澄清问题。
    """

    candidates = result.get("candidates", [])

    suggestions = []

    for item in candidates[:3]:
        suggestions.append(
            {
                "metric_name": item["name"],
                "metric_label": item["chinese_name"],
            }
        )

    return {
        "status": "needs_clarification",
        "question": result["question"],
        "message": "问题存在歧义，请选择您想查询的指标：",
        "suggestions": suggestions,
    }


if __name__ == "__main__":

    mock_result = {
        "status": "needs_clarification",
        "question": "最赚钱",
        "candidates": [
            {
                "name": "item_sales_amount",
                "chinese_name": "商品明细实付销售额",
                "score": 0.41,
            },
            {
                "name": "refund_rate",
                "chinese_name": "退款率",
                "score": 0.39,
            },
            {
                "name": "order_paid_amount",
                "chinese_name": "订单实付金额",
                "score": 0.33,
            },
        ],
    }

    print(
        build_clarification(mock_result)
    )
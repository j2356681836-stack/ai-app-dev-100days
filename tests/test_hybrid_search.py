from app.semantic_layer.hybrid_search import search_metric

questions = [
    "卖得最好",
    "最赚钱",
    "销售冠军",
    "退货最严重",
    "退款最多",
    "订单最多",
    "成交最多",
    "销量最高",
]

for question in questions:
    result = search_metric(question)

    print("=" * 60)
    print(question)
    print(result)
from app.semantic_layer.semantic_search_v2 import search_metric_by_embedding

questions = [
    "卖得最好",
    "最赚钱",
    "销售冠军",
    "退货最严重",
    "退款最多",
    "订单最多",
    "成交最多",
    "销量最高",
    "表现最差",
    "销售最差"
]

for question in questions:
    result = search_metric_by_embedding(question)

    print("=" * 60)
    print("Question:")
    print(result["question"])

    print(result["candidates"][0]["chinese_name"])
    print(result["candidates"][0]["score"])

    print(result["candidates"][1]["chinese_name"])
    print(result["candidates"][1]["score"])

    print(f"gap = {result['candidates'][0]['score'] - result['candidates'][1]['score']}")



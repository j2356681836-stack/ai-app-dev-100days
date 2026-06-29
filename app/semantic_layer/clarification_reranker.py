def infer_query_tags(query: str) -> set[str]:
    """
    根据用户问题提取轻量业务语义标签。

    注意：
    这里不是最终意图解析器，也不直接决定 metric。
    它只用于 needs_clarification 场景下的候选重排。
    """

    tags = set()

    if any(word in query for word in ["赚钱", "盈利", "利润", "收益", "收入"]):
        tags.add("profit")

    if any(word in query for word in ["划算", "投放效率", "回报", "ROI", "roi"]):
        tags.add("efficiency")

    if any(word in query for word in ["拉新", "获客", "新客"]):
        tags.add("acquisition")

    if any(word in query for word in ["退款", "退货", "售后", "退得"]):
        tags.add("refund")

    if any(word in query for word in ["渠道"]):
        tags.add("channel")

    if any(word in query for word in ["品类", "商品"]):
        tags.add("product")

    return tags


def score_candidate_for_query(
    query: str,
    candidate: dict,
) -> float:
    """
    对 embedding candidate 做轻量业务重排。

    输入：
    - query: 用户问题
    - candidate: semantic_search_v2 返回的候选，包含 name / score

    输出：
    - rerank_score: 原 embedding score + 轻量业务加权
    """

    tags = infer_query_tags(query)
    metric_name = candidate["name"]
    score = candidate.get("score", 0)

    bonus = 0.0
    penalty = 0.0

    if "profit" in tags:
        if metric_name in ["roi", "channel_sales_amount", "item_sales_amount", "order_paid_amount"]:
            bonus += 0.10

        if metric_name == "cac":
            penalty += 0.30

        if metric_name in ["refund_rate", "channel_refund_rate"]:
            penalty += 0.20

    if "efficiency" in tags:
        if metric_name == "roi":
            bonus += 0.16

        if metric_name == "cac":
            bonus += 0.04

        if metric_name in ["refund_rate", "channel_refund_rate"]:
            penalty += 0.20

    if "acquisition" in tags:
        if metric_name == "cac":
            bonus += 0.12

        if metric_name == "roi":
            bonus += 0.04

        if metric_name in ["refund_rate", "channel_refund_rate"]:
            penalty += 0.30

    if "refund" in tags:
        if metric_name in ["refund_rate", "channel_refund_rate"]:
            bonus += 0.10

    return score + bonus - penalty


def rerank_candidates_for_clarification(
    query: str,
    candidates: list[dict],
    top_k: int = 3,
) -> list[dict]:
    """
    只在 clarification 场景下使用的候选重排。

    不改变 embedding 是否 confident。
    不改变 matched / needs_clarification 判断。
    只改变 clarification suggestions 的顺序和候选质量。
    """

    reranked = []

    for candidate in candidates:
        item = candidate.copy()
        item["original_score"] = candidate.get("score")
        item["rerank_score"] = score_candidate_for_query(query, candidate)
        reranked.append(item)

    reranked.sort(
        key=lambda x: x["rerank_score"],
        reverse=True,
    )

    return reranked[:top_k]
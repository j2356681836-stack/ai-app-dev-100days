import re
from typing import Any


CHINESE_NUMBER_MAP = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def parse_limit(question: str) -> int | None:
    """
    从问题中解析 LIMIT。

    规则：
    1. top3 / Top3 → 3
    2. 前3 → 3
    3. 前三 → 3
    4. 3个渠道 / 三个渠道 → 3
    5. 最高 / 最低 / 最大 / 最小 等极值词 → 1
    6. 各渠道排名 / 排名 → None
    """

    # 用 re.search 识别 top + 数字
    # 例如：渠道ROI Top3
    # 命中后 return int(...)
    top_match = re.search(r"top\s*(\d+)",question,re.IGNORECASE)
    if top_match:
        return int(top_match.group(1))      # group(1) 返回 (\d+)的内容

    # 识别 “前3”
    # 命中后 return int(...)
    front_digit_match = re.search(r"前\s*(\d+)",question)
    if front_digit_match:
        return int(front_digit_match.group(1))      # group(1) 返回 (\d+)的内容

    # 识别 “前三”
    # 命中后从 CHINESE_NUMBER_MAP 取值
    front_chinese_match = re.search(r"前\s*([一二三四五六七八九十])",question)
    if front_chinese_match:
        return CHINESE_NUMBER_MAP[front_chinese_match.group(1)]      # group(1) 返回 (\d+)的内容

    # 识别 “3个渠道 / 3个品类 / 3条”
    # 命中后 return int(...)
    amount_digit_match = re.search(r"(\d+)\s*(个|名|家|条|种|类|款|渠道|品类)",question)
    if amount_digit_match:
        return int(amount_digit_match.group(1))      # group(1) 返回 (\d+)的内容

    # 识别 “三个渠道 / 三个品类 / 三条”
    # 命中后从 CHINESE_NUMBER_MAP 取值
    amount_chinese_match = re.search(r"([一二两三四五六七八九十])\s*(个|名|家|条|种|类|款|渠道|品类)",question)
    if amount_chinese_match:
        return CHINESE_NUMBER_MAP[amount_chinese_match.group(1)]      # group(1) 返回 (\d+)的内容

    top1_keywords = [
        "最高",
        "最低",
        "最大",
        "最小",
        "最多",
        "最少",
        "第一",
        "最划算",
        "最严重",
        "最厉害",
    ]

    # 如果 question 中包含 top1_keywords 任意一个词
    # return 1
    if any(key_word in question for key_word in top1_keywords):
        return 1

    return None


def parse_sort_hint(question: str) -> str | None:
    """
    从问题中解析用户显式表达的排序方向。
    """

    asc_keywords = ["最低", "最小", "最少", "升序", "从低到高"]
    desc_keywords = ["最高", "最大", "最多", "降序", "从高到低"]

    # 如果包含 asc_keywords 中任意一个，return "asc"
    if any(key_word in question for key_word in asc_keywords):
        return 'asc'

    # 如果包含 desc_keywords 中任意一个，return "desc"
    if any(key_word in question for key_word in desc_keywords):
        return 'desc'

    return None


def parse_dimension(question: str) -> str | None:
    """
    从问题中解析维度。
    """

    # 如果问题包含 “渠道”，return "channel"
    if "渠道" in question:
        return "channel"

    # 如果问题包含 “品类” 或 “类目”，return "category"
    if "品类" in question or "类目" in question:
        return "category"

    return None


def parse_ranking_type(question: str, limit: int | None) -> str:
    """
    根据 question 和 limit 判断排名类型。
    """
    # 如果 limit == 1，return "top1"
    if limit == 1:
        return "top1"

    # 如果 limit > 1，return "topn"
    if limit is not None and limit > 1:
        return "topn"

    ranking_keywords = ["排名", "排行", "排序", "各"]

    # 如果问题包含 ranking_keywords 任意一个，return "ranking"
    if any(key_word in question for key_word in ranking_keywords):
        return "ranking"

    return "unknown"


def parse_intent(question: str) -> dict[str, Any]:
    """
    解析用户问题，返回结构化 intent。
    """
    limit = parse_limit(question)

    return {
        "question": question,
        "limit": limit,
        "ranking_type": parse_ranking_type(question, limit),
        "sort_hint": parse_sort_hint(question),
        "dimension": parse_dimension(question),
    }


if __name__ == "__main__":
    questions = [
        "哪个渠道ROI最高",
        "各渠道ROI排名",
        "渠道ROI Top3",
        "渠道ROI前3",
        "获客成本最低的三个渠道",
        "获客成本最低的3个渠道",
        "获客成本前五渠道",
        "各品类退款率排名",
    ]

    for question in questions:
        print(question)
        print(parse_intent(question))
        print("-" * 80)
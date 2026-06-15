import re

from app.semantic_layer.query_plan_loader import get_query_plan_by_metric
from app.semantic_layer.intent_parser import parse_intent


def parse_limit(question: str) -> int | None:
    """
    从用户问题中解析 LIMIT。

    返回：
    - N：TopN / 前N / N个 / 中文数字 等问题
    - 1：只有极值表达且没有明确数量时
    - None：排名类问题，不限制行数
    """

    chinese_number_map = {
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

    # 1. 英文/混合写法：Top5、top10、TOP 3
    top_match = re.search(r"top\s*(\d+)", question, re.IGNORECASE)
    if top_match:
        return int(top_match.group(1))

    # 2. 中文阿拉伯数字：前3、前 5 个、前10名
    front_digit_match = re.search(r"前\s*(\d+)", question)
    if front_digit_match:
        return int(front_digit_match.group(1))

    # 3. 中文数字：前三、前五、前十
    front_chinese_match = re.search(r"前\s*([一二两三四五六七八九十])", question)
    if front_chinese_match:
        return chinese_number_map[front_chinese_match.group(1)]

    # 4. “最低的三个渠道”“最高的5个渠道”“最划算的三家”
    amount_digit_match = re.search(r"(\d+)\s*(个|名|家|条|种|类|款|渠道|品类)", question)
    if amount_digit_match:
        return int(amount_digit_match.group(1))

    amount_chinese_match = re.search(r"([一二两三四五六七八九十])\s*(个|名|家|条|种|类|款|渠道|品类)", question)
    if amount_chinese_match:
        return chinese_number_map[amount_chinese_match.group(1)]

    # 5. 只有极值表达，没有明确数量时，才认为是 Top1
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

    if any(keyword in question for keyword in top1_keywords):
        return 1

    # 6. 排名类问题默认不限制
    return None


def build_limit_clause(question: str) -> str:
    limit = parse_limit(question)

    if limit is None:
        return ""

    return f"LIMIT {limit}"


def build_limit_clause_from_intent(intent: dict) -> str:
    """
    根据 intent 构建 LIMIT 子句。
    """
    limit = intent.get("limit")

    if limit is None:
        return ""

    return f"LIMIT {limit}"


def get_template_config(metric_name: str) -> dict:
    """
    获取模板生成所需的 query plan 配置。
    当前 V1 从 metadata/query_plans.yaml 中读取。
    """
    plan = get_query_plan_by_metric(metric_name)

    if not plan:
        raise ValueError(f"未找到指标对应的 query plan: {metric_name}")

    return plan


def build_order_by_clause(plan: dict) -> str:
    """
    根据 query plan 构建 ORDER BY 子句。
    """
    default_sort = plan.get("default_sort", {})
    field = default_sort.get("field")
    direction = default_sort.get("direction", "desc").upper()

    if not field:
        raise ValueError("query plan 缺少 default_sort.field")

    return f"ORDER BY {field} {direction}"
    

def build_formula_expression(
    base_expression: str,
    plan: dict,
) -> str:
    """
    根据 query plan 的 output.formula 配置构建最终表达式。

    当前支持：
    - multiply_by_100: 是否乘以 100
    - round: 保留小数位
    """
    formula_config = plan.get("output", {}).get("formula", {})

    multiply_by_100 = formula_config.get("multiply_by_100", False)
    round_digits = formula_config.get("round", 2)

    expression = base_expression

    if multiply_by_100:
        expression = f"({expression}) * 100"

    return f"ROUND({expression}, {round_digits})"


def generate_roi_sql_from_intent(intent: dict) -> str:
    question = intent.get("question", "")
    limit_clause = build_limit_clause_from_intent(intent)
    return generate_roi_sql(question, limit_clause=limit_clause)


def generate_roi_sql(question: str, limit_clause: str | None = None) -> str:
    """
    Generate stable ROI SQL from template.

    ROI = channel_sales_amount / marketing_spend_amount

    关键规则：
    - ROI 不乘以 100
    - 使用订单与投放的重叠时间窗口
    - 先分别按 channel_id 聚合订单销售额和营销花费
    - 再 JOIN 聚合结果
    - ROI 越高越好，默认 DESC
    """
    plan = get_template_config("roi")
    order_by_clause = build_order_by_clause(plan)
    output_alias = plan["output"]["formula"]["alias"]
    if limit_clause is None:
        limit_clause = build_limit_clause(question)
    formula_expression = build_formula_expression(
        base_expression="cs.sales_amount / NULLIF(csp.spend_amount, 0)",
        plan=plan,
    )

    sql = f"""
WITH date_window AS (
    SELECT
        GREATEST(
            (SELECT MIN(order_date)::date FROM fact_orders WHERE order_status = 'paid'),
            (SELECT MIN(spend_date) FROM fact_marketing_spend)
        ) AS start_date,
        LEAST(
            (SELECT MAX(order_date)::date FROM fact_orders WHERE order_status = 'paid'),
            (SELECT MAX(spend_date) FROM fact_marketing_spend)
        ) AS end_date
),
channel_sales AS (
    SELECT
        fo.channel_id,
        SUM(fo.paid_amount) AS sales_amount
    FROM fact_orders fo
    CROSS JOIN date_window dw
    WHERE fo.order_status = 'paid'
      AND fo.order_date::date BETWEEN dw.start_date AND dw.end_date
    GROUP BY fo.channel_id
),
channel_spend AS (
    SELECT
        fms.channel_id,
        SUM(fms.spend_amount) AS spend_amount
    FROM fact_marketing_spend fms
    CROSS JOIN date_window dw
    WHERE fms.spend_date BETWEEN dw.start_date AND dw.end_date
    GROUP BY fms.channel_id
)
SELECT
    dc.channel_name,
    {formula_expression} AS {output_alias}
FROM channel_sales cs
JOIN channel_spend csp
    ON cs.channel_id = csp.channel_id
JOIN dim_channel dc
    ON cs.channel_id = dc.channel_id
{order_by_clause}
{limit_clause};;
"""

    return sql.strip()


def generate_cac_sql_from_intent(intent: dict) -> str:
    question = intent.get("question", "")
    limit_clause = build_limit_clause_from_intent(intent)
    return generate_cac_sql(question, limit_clause=limit_clause)


def generate_cac_sql(question: str, limit_clause: str | None = None) -> str:
    """
    Generate stable CAC SQL from template.

    CAC = marketing_spend_amount / acquired_customer_count

    关键规则：
    - CAC 越低越好，默认 ASC
    - 使用订单与投放的重叠时间窗口
    - 先在全量 paid 订单中计算真实首单
    - 再判断真实首单是否落在时间窗口内
    - 按真实首单 channel_id 统计获客客户数
    - 按 channel_id 聚合营销花费
    """
    plan = get_template_config("cac")
    order_by_clause = build_order_by_clause(plan)
    output_alias = plan["output"]["formula"]["alias"]
    if limit_clause is None:
        limit_clause = build_limit_clause(question)
    formula_expression = build_formula_expression(
        base_expression="cs.marketing_spend_amount / NULLIF(ac.acquired_customer_count, 0)",
        plan=plan,
    )

    sql = f"""
WITH date_window AS (
    SELECT
        GREATEST(
            (SELECT MIN(order_date)::date FROM fact_orders WHERE order_status = 'paid'),
            (SELECT MIN(spend_date) FROM fact_marketing_spend)
        ) AS start_date,
        LEAST(
            (SELECT MAX(order_date)::date FROM fact_orders WHERE order_status = 'paid'),
            (SELECT MAX(spend_date) FROM fact_marketing_spend)
        ) AS end_date
),
first_paid_order AS (
    SELECT
        fo.customer_id,
        fo.channel_id,
        fo.order_date,
        ROW_NUMBER() OVER (
            PARTITION BY fo.customer_id
            ORDER BY fo.order_date ASC
        ) AS rn
    FROM fact_orders fo
    WHERE fo.order_status = 'paid'
),
acquired_customers AS (
    SELECT
        fpo.channel_id,
        COUNT(DISTINCT fpo.customer_id) AS acquired_customer_count
    FROM first_paid_order fpo
    CROSS JOIN date_window dw
    WHERE fpo.rn = 1
      AND fpo.order_date::date BETWEEN dw.start_date AND dw.end_date
    GROUP BY fpo.channel_id
),
channel_spend AS (
    SELECT
        fms.channel_id,
        SUM(fms.spend_amount) AS marketing_spend_amount
    FROM fact_marketing_spend fms
    CROSS JOIN date_window dw
    WHERE fms.spend_date BETWEEN dw.start_date AND dw.end_date
    GROUP BY fms.channel_id
)
SELECT
    dc.channel_name,
    {formula_expression} AS {output_alias}
FROM channel_spend cs
JOIN acquired_customers ac
    ON cs.channel_id = ac.channel_id
JOIN dim_channel dc
    ON cs.channel_id = dc.channel_id
{order_by_clause}
{limit_clause};
"""

    return sql.strip()

def generate_template_sql_from_intent(
    metric_name: str,
    intent: dict,
) -> str | None:
    """
    根据 metric_name 和 intent 生成模板 SQL。
    当前支持：
    - roi
    - cac
    """
    if metric_name == "roi":
        return generate_roi_sql_from_intent(intent)

    if metric_name == "cac":
        return generate_cac_sql_from_intent(intent)

    return None


def generate_template_sql(metric_name: str, question: str) -> str | None:
    """
    根据 metric_name 生成模板 SQL。

    当前 V1 支持：
    - roi
    - cac

    如果没有对应模板，返回 None。
    """

    if metric_name == "roi":
        return generate_roi_sql(question)

    if metric_name == "cac":
        return generate_cac_sql(question)

    return None
    

if __name__ == "__main__":
    print("Top1 ROI SQL:")
    print(generate_roi_sql("哪个渠道ROI最高"))

    print()
    print("=" * 80)
    print()

    print("Ranking ROI SQL:")
    print(generate_roi_sql("各渠道ROI排名"))

    print()
    print("=" * 80)
    print()

    print("Top1 CAC SQL:")
    print(generate_cac_sql("哪个渠道获客成本最低"))

    print()
    print("=" * 80)
    print()

    print("Ranking CAC SQL:")
    print(generate_cac_sql("各渠道获客成本排名"))
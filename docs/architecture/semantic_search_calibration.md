# Semantic Search Calibration

## 背景

Day34 对 Semantic Search V2 进行了校准，为了避免 Embedding Search 在低置信度或语义接近时强行返回错误指标。

## 当前阈值

` 
TOP1_THRESHOLD = 0.50
GAP_THRESHOLD = 0.08
`

## 判断逻辑

当满足以下条件时，Embedding 结果才被认为可信：
- Top1 Score >= 0.50
- Top1 Score - Top2 Score >= 0.08
否则进入 Clarification。

## 校准样例

| Query | Top1      | Top1 Score | Top2      |   Gap | Decision            |
| ----- | --------- | ---------: | --------- | ----: | ------------------- |
| 销售冠军  | 商品明细实付销售额 |      0.556 | 订单实付金额    | 0.111 | matched             |
| 退款最多  | 退款率       |      0.600 | 商品明细实付销售额 | 0.102 | matched             |
| 最赚钱   | 商品明细实付销售额 |      0.510 | 订单实付金额    | 0.081 | needs_clarification |
| 订单最多  | 商品明细实付销售额 |      0.546 | 订单实付金额    | 0.019 | needs_clarification |

## 当前结论：
- Alias Search 仍然作为最高优先级。
- Embedding Search 负责语义泛化。
- Confidence 判断统一放在 semantic_search_v2.py。
- Hybrid Search 只负责路由，不再重复判断阈值。

## 当前限制

当前指标体系仍较少，因此：
- 订单最多
- 成交最多
- 销量最高
这类问题缺少独立指标支撑，后续应新增：
- 订单数
- 成交订单数
- 销售件数
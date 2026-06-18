# Day43 学习日志

## 今日主题

Phase2：Business Semantic Layer & Text-to-SQL

Day43: 普通指标 Intent Cases 收尾 & Result-level Evaluation V2

---

## 今日学习目标

今天目标不是继续无限扩展普通指标，而是完成普通指标 LLM 路径的阶段性收口，并升级 Result-level Evaluation。

重点验证：
- 普通指标 TopN
- 普通指标反向排序
- 普通指标低值 TopN
- Intent Context 对 LLM SQL 的约束效果
- 多行结果值校验能力

---

## 完成内容一：普通指标 Intent Cases 收尾

新增 Golden Cases：
- case_029：品类退款率Top3
- case_030：品类退款率从低到高排名
- case_031：销量最低的三个品类

覆盖能力：
- limit 解析
- ranking_type 解析
- sort_hint 解析
- final_sort_direction 约束
- category 维度识别
- generation_method = llm 校验
- 普通指标 TopN
- 普通指标反向排序
- 普通指标低值 TopN
- ORDER BY 校验
- LIMIT 校验

---

## 新增 Case 验证结果

case_029：品类退款率Top3

验证点：
- generation_method = llm
- limit = 3
- ranking_type = topn
- dimension = category
- SQL 使用 ORDER BY refund_rate_pct DESC
- SQL 使用 LIMIT 3

返回结果：
- 精华：10.0
- 防晒：4.55
- 面膜：4.48

---

case_030：品类退款率从低到高排名

验证点：
- generation_method = llm
- ranking_type = ranking
- sort_hint = asc
- final_sort_direction = asc
- dimension = category
- SQL 使用 ORDER BY refund_rate_pct ASC
- SQL 不添加 LIMIT

返回结果：
- 面霜：4.37
- 洁面：4.47
- 面膜：4.48
- 防晒：4.55
- 精华：10.0

---

case_031：销量最低的三个品类

验证点：
- generation_method = llm
- limit = 3
- ranking_type = topn
- sort_hint = asc
- final_sort_direction = asc
- dimension = category
- SQL 使用 ORDER BY sales_quantity ASC
- SQL 使用 LIMIT 3

返回结果：
- 面霜：6925
- 面膜：6994
- 精华：7039

---

## 完成内容二：Result-level Evaluation V2

新增 evaluator 能力：
- check_expected_rows
- expected_rows 多行结果校验
- rows_mismatches 报告字段
- evaluator passed 判断纳入 rows_mismatches
- evaluation JSON 报告输出 rows_mismatches

expected_rows 用于校验：
- 行顺序
- 每一行对象
- 每一行数值
- 数值字段支持 tolerance 误差

---

## expected_result / expected_order / expected_rows 区别

expected_result：适合 Top1 问题，只检查第一行结果。

例如：
- 哪个渠道销售额最高
- 哪个渠道 ROI 最高
- 哪个渠道获客成本最低

---

expected_order：适合轻量排名问题，只检查某个字段的排序顺序。

例如：
- 各渠道销售额排名
- 各渠道 ROI 排名

---

expected_rows：适合 TopN / Ranking / 多行结果强校验。

它可以同时检查：
- 第 1 行是谁
- 第 1 行数值是多少
- 第 2 行是谁
- 第 2 行数值是多少
- 第 N 行是谁
- 第 N 行数值是多少

---

## 验证结果

当前 evaluator 结果：
Total: 26
Passed: 26
Failed: 0
Pass Rate: 100.0%

测试报告：docs/evaluation/evaluation_20260618_150826.json

---

## 关键结论

普通指标接入 Intent Context 后，价值不是让简单 SQL 从错变对，而是让系统从“LLM 自由理解问题”升级为“结构化 intent 约束 SQL 生成”。

当前普通指标 LLM 路径已经稳定覆盖：
- TopN
- 从低到高排序
- 最低的三个
- category 维度
- 稳定字段别名
- ORDER BY
- LIMIT

Result-level Evaluation V2 让 evaluator 从“只检查第一行或排序顺序”，升级为“检查多行对象和多行数值”。
这为后续 Answer Layer 打基础。因为中文业务回答必须建立在可信表格结果之上。

---

## 技术债

1. 普通指标目前没有 query_plan，因此 sort_field 通常为 None。
2. 普通指标没有指标级 default_sort。
3. 部分 TopN 默认排序方向仍依赖 LLM 对自然语言的理解。
4. 后续可考虑为普通指标增加 lightweight query_plan / default_sort metadata。
5. evaluator 的 JSON report 保存逻辑仍有重复，后续可统一 report writer。
6. prompt_builder.py 规则数量继续增长，后续 Day47 需要模块化收束。


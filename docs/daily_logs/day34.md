## Day34：Semantic Search Calibration + Explainability

完成内容：
- 完成 Semantic Search Calibration
- 将 TOP1_THRESHOLD 调整为 0.50
- 将 GAP_THRESHOLD 调整为 0.08
- 优化 Metric Text，新增 examples 和 negative_examples
- 删除 hybrid_search.py 中重复的二次阈值判断
- 将置信度判断统一收敛到 semantic_search_v2.py
- 新增 Search Trace，支持查看 alias / embedding / clarification 的检索过程
- 新增 docs/architecture/semantic_search_calibration.md
- Evaluation 回归测试 8/8 通过

关键收获：
- matched 不等于可信，需要结合 score 和 gap 判断
- Confidence 判断应该只有一个来源，避免多处阈值造成维护混乱
- Trace 能帮助定位问题来自 Alias、Embedding、Clarification 还是后续 SQL 链路
- 当前指标体系仍不足，订单最多、成交最多、销量最高后续需要新增独立指标

当前状态：
- Hybrid Search 可解释性增强完成
- Semantic Search V2 进入可校准、可追踪状态
- Evaluation 仍保持 100%
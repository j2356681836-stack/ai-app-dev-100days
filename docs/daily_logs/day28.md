# Day28

## 学习目标
实现 Text2SQL 执行层闭环。

## 完成内容
- 创建 database.py
- 创建 sql_runner.py
- 创建 result_formatter.py
- 创建 query_service.py
- 支持 SQL 执行
- 支持 Decimal 转换
- 支持统一返回结构
- 支持执行耗时统计

## 关键收获
Engine 负责数据库连接池管理。
SessionLocal 用于后续事务管理和 ORM。
SQLAlchemy 2.0 推荐使用 text() 执行原生 SQL。

Text2SQL 项目真正闭环需要：
Question → SQL → Execute → Result
而不仅仅是生成 SQL。

## 遇到的问题
1. 缺少 database.py 导致无法导入 engine。
2. Decimal 无法直接序列化。
3. 比率指标精度过高。
4. “最高”场景偶发缺少 LIMIT 1。

## 解决方案
- 抽取数据库连接模块。
- 增加 Result Formatter。
- Prompt 中增加比率指标规范。
- Prompt 中增加 Top1 排序规则。
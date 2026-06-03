# 2026-05-27 — Phase 2 Day 21-22

## 今日目标

建立企业级 AI BI Agent 的数据库基础设施：

- PostgreSQL
- pgvector
- SQLAlchemy 2.0
- 美妆业务数据库 Schema

---

# 今日完成

## 1. PostgreSQL + pgvector 环境完成

完成：

- Docker Desktop 配置
- PostgreSQL 容器启动
- pgvector 0.8.2 启用
- SQLAlchemy 2.0 连接
- .env 配置管理

成功验证：

- PostgreSQL 连接成功
- vector extension 启用成功
- 向量距离计算成功

---

## 2. 建立美妆业务数据库 Schema

完成 8 张核心业务表：

### 维度表（Dimension Tables）

- dim_product
- dim_customer
- dim_channel

### 事实表（Fact Tables）

- fact_orders
- fact_order_items
- fact_refunds
- fact_marketing_spend
- fact_reviews

---

# 今日关键理解

## 1. 什么是企业级业务数据库

之前更偏向“练习 SQL”。

今天第一次真正开始：

- 业务建模
- 维度表 / 事实表
- 订单链路
- ROI 与退款关系

开始理解：

“业务问题如何映射到数据关系”。

---

## 2. 为什么退款必须独立成表

退款不是订单的一个字段。

退款是：

- 独立业务事件
- 可能部分退款
- 可能多次退款
- 可能延迟退款

因此：

fact_refunds 必须独立设计。

---

## 3. 为什么需要 Semantic Layer

用户不会问：

“请查询 fact_orders 并 group by month”。

用户会问：

“xx渠道 ROI 为什么下降？”

因此系统必须：

- 理解业务指标
- 理解业务口径
- 自动检索相关 schema
- 自动生成 SQL

---

# 今日踩坑

## 1. PowerShell 不支持 `< file.sql`

错误：

RedirectionNotSupported

解决：

使用：

Get-Content xxx.sql | docker exec -i ... psql

而不是：

psql < xxx.sql

---

## 2. 开始意识到项目结构问题

之前：

phase/day 更偏向学习记录。

现在：

开始需要真正的工程结构：

app/db
app/semantic_layer
app/text_to_sql

但 phase 文件夹仍然保留，作为学习实验区。

---

# 当前项目状态

当前已完成：

✅ PostgreSQL
✅ pgvector
✅ SQLAlchemy
✅ 美妆业务 Schema

下一步：

- 生成模拟业务数据
- 构建 Business Semantic Layer
- 建立 Text-to-SQL 检索链路

---

# 明日计划

1. 建立 seed.py
2. 生成模拟美妆业务数据
3. 植入业务规律（ROI 下滑、退款异常等）
4. 开始构建业务指标字典
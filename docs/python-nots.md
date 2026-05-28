1️⃣ **conn** = 数据库连接对象，作用：Python ↔ PostgreSQL
2️⃣ **execute()** = 执行SQL


| 方法                | 作用      |
| -----------------   | -----     |
| `conn.execute()`    | 执行SQL   |
| `conn.commit()`     | 提交事务   |
| `conn.rollback()`   | 回滚       |
| `conn.close() `     | 关闭连接   |


`text()`是 SQLAlchemy的**SQL文本包装器**，意思：“这是原生SQL，请按SQL处理”
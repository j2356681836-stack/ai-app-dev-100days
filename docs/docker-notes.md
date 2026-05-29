# Docker 常用命令

---

1. 启动容器

`docker compose up -d`  后台启动 docker-compose.yml 中定义的服务

---

2. 查看运行状态

`docker compose ps` 查看容器是否正常运行

---

3. 进入 PostgreSQL

`docker exec -it pgvector-db psql -U postgres`  进入数据库命令行，用于执行 SQL

| 部分          | 含义               |
| ----------- | ---------------- |
| docker exec | 在运行中的容器里执行命令     |
| -it         | 交互式终端            |
| pgvector-db | 容器名字             |
| psql        | PostgreSQL 命令行工具 |
| -U postgres | 用 postgres 用户登录  |

---

`docker exec -it beauty_agent_pg psql -U admin -d beauty_kb` 进入数据库，回复**beauty_kb=#**后可以写SQL语句进行查询

| 部分              | 含义                 |
| --------------- | ------------------ |
| beauty_agent_pg | 你的项目数据库容器          |
| -U admin        | 用 admin 用户登录       |
| -d beauty_kb    | 指定连接 beauty_kb 数据库 |





`docker ps` 进入 PostgreSQL

\i sql/daily_sales.sql



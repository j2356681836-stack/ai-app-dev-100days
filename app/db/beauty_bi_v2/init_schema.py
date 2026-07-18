from pathlib import Path

from app.db.database import engine


V2_SCHEMA_NAME = "beauty_bi_v2"
SCHEMA_SQL_PATH = Path(__file__).with_name("schema.sql")


def load_schema_sql() -> str:
    """
    读取 Beauty BI V2 DDL。
    """
    if not SCHEMA_SQL_PATH.exists():
        raise FileNotFoundError(
            f"V2 schema.sql 不存在：{SCHEMA_SQL_PATH}"
        )

    schema_sql = SCHEMA_SQL_PATH.read_text(
        encoding="utf-8"
    )

    if not schema_sql.strip():
        raise ValueError(
            "V2 schema.sql 不能为空。"
        )

    return schema_sql


def init_v2_schema() -> None:
    """
    在 beauty_kb 数据库中创建独立的
    beauty_bi_v2 Schema，并执行 V2 DDL。

    安全策略：
    - 不操作 public；
    - 如果 V2 Schema 已有表，则拒绝覆盖；
    - 任意异常都会回滚。
    """
    schema_sql = load_schema_sql()

    raw_connection = engine.raw_connection()
    cursor = None

    try:
        cursor = raw_connection.cursor()

        cursor.execute(
            f'CREATE SCHEMA IF NOT EXISTS '
            f'"{V2_SCHEMA_NAME}"'
        )

        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (V2_SCHEMA_NAME,),
        )

        existing_tables = [
            row[0]
            for row in cursor.fetchall()
        ]

        if existing_tables:
            raise RuntimeError(
                "beauty_bi_v2 Schema 已存在数据表，"
                "为防止误覆盖，本次初始化已停止："
                f"{existing_tables}"
            )

        # 让 schema.sql 中没有显式 Schema 前缀的表，
        # 全部创建到 beauty_bi_v2，而不是 public。
        cursor.execute(
            f'SET LOCAL search_path TO '
            f'"{V2_SCHEMA_NAME}"'
        )

        # schema.sql 包含多条 DDL，因此使用 psycopg
        # 的 simple-query 模式执行完整脚本。
        cursor.execute(
            schema_sql,
            prepare=False,
        )

        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (V2_SCHEMA_NAME,),
        )

        created_tables = [
            row[0]
            for row in cursor.fetchall()
        ]

        if "dim_date" not in created_tables:
            raise RuntimeError(
                "V2 DDL 执行后仍未发现 dim_date。"
            )

        raw_connection.commit()

    except Exception:
        raw_connection.rollback()
        raise

    finally:
        if cursor is not None:
            cursor.close()

        raw_connection.close()

    print("Beauty BI V2 schema initialization passed.")
    print(f"Target schema: {V2_SCHEMA_NAME}")
    print(f"Created tables: {len(created_tables)}")
    print(f"Tables: {created_tables}")


if __name__ == "__main__":
    init_v2_schema()